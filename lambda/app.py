import os
import csv
import io
import json
import logging
import re
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

TZ = ZoneInfo(os.environ.get("SCHEDULE_TZ", "America/Los_Angeles"))

# Cost Explorer endpoint is us-east-1
CE_REGION = "us-east-1"

ssm = boto3.client("ssm")
ce = boto3.client("ce", region_name=CE_REGION)
s3 = boto3.client("s3")
# SES uses the infrastructure region (AWS_REGION is automatically set by Lambda runtime)
ses = boto3.client("ses", region_name=os.environ.get("SES_REGION", os.environ.get("AWS_REGION", "us-east-1")))
cloudwatch = boto3.client("cloudwatch")

PARAM_REPORT_TO = os.environ["PARAM_REPORT_TO"]
PARAM_REPORT_FROM = os.environ["PARAM_REPORT_FROM"]
PARAM_ARCHIVE_BUCKET = os.environ["PARAM_ARCHIVE_BUCKET"]
PARAM_TOP_N_SERVICES = os.environ["PARAM_TOP_N_SERVICES"]
PARAM_INCLUDE_MTD = os.environ["PARAM_INCLUDE_MTD"]
PARAM_INCLUDE_DRIVERS = os.environ["PARAM_INCLUDE_DRIVERS"]

ENABLE_METRICS = os.environ.get("ENABLE_METRICS", "true").lower() == "true"
METRICS_NAMESPACE = os.environ.get("METRICS_NAMESPACE", "cost-alerting")

_cache = {}


def get_params(names):
    """Fetch SSM parameters with caching."""
    missing = [n for n in names if n not in _cache]
    if missing:
        try:
            resp = ssm.get_parameters(Names=missing, WithDecryption=True)
            for p in resp.get("Parameters", []):
                _cache[p["Name"]] = p["Value"]
        except Exception as e:
            logger.error(f"Failed to fetch SSM parameters: {e}")
            raise
    return {n: _cache[n] for n in names}


def to_bool(s: str) -> bool:
    """Convert string to boolean."""
    return str(s).lower() in ("1", "true", "yes", "y", "on")


def money(amount_str: str) -> float:
    """Convert cost amount string to float."""
    try:
        return float(amount_str)
    except Exception:
        return 0.0


def put_metric(metric_name, value, unit="Count"):
    """Put custom CloudWatch metric."""
    if not ENABLE_METRICS:
        return

    try:
        cloudwatch.put_metric_data(
            Namespace=METRICS_NAMESPACE,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": unit,
                    "Timestamp": datetime.utcnow(),
                }
            ],
        )
    except Exception as e:
        logger.warning(f"Failed to put metric {metric_name}: {e}")


def ce_grouped_cost(start: date, end: date, group_key: str):
    """
    Query Cost Explorer grouped by dimension.
    GroupBy supports up to two group keys; we use one per request.
    """
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": group_key}],
        )
        result = resp["ResultsByTime"][0]
        groups = result.get("Groups", [])
        rows = []
        total = 0.0
        for g in groups:
            key = g["Keys"][0]
            amt = money(g["Metrics"]["UnblendedCost"]["Amount"])
            if amt > 0:
                rows.append((key, amt))
                total += amt
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows, total, resp
    except Exception as e:
        logger.error(f"Cost Explorer query failed for {group_key}: {e}")
        raise


def csv_bytes(headers, rows):
    """Generate CSV bytes from headers and rows."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def put_s3(bucket, key, body_bytes, content_type):
    """Upload object to S3 with encryption."""
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body_bytes,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        logger.info(f"Uploaded to s3://{bucket}/{key}")
    except Exception as e:
        logger.error(f"Failed to upload to S3 {key}: {e}")
        raise


def html_table(title, rows, total):
    """Generate HTML table for email."""
    trs = "\n".join(
        f"<tr><td style='padding:6px 10px;border:1px solid #ddd'>{k}</td>"
        f"<td style='padding:6px 10px;border:1px solid #ddd;text-align:right'>${v:,.2f}</td></tr>"
        for k, v in rows
    )
    if not trs:
        trs = "<tr><td colspan='2' style='padding:6px 10px;border:1px solid #ddd'>No charges</td></tr>"
    return f"""
      <h3 style="margin:16px 0 8px 0;">{title}</h3>
      <table style="border-collapse:collapse;">
        <thead>
          <tr>
            <th style="padding:6px 10px;border:1px solid #ddd;text-align:left;">Key</th>
            <th style="padding:6px 10px;border:1px solid #ddd;text-align:right;">Amount</th>
          </tr>
        </thead>
        <tbody>
          {trs}
          <tr>
            <td style="padding:6px 10px;border:1px solid #ddd;"><b>Total</b></td>
            <td style="padding:6px 10px;border:1px solid #ddd;text-align:right;"><b>${total:,.2f}</b></td>
          </tr>
        </tbody>
      </table>
    """


def html_to_text(html_body):
    """Convert HTML email to plain text for better deliverability."""
    # Simple HTML to text conversion
    text = html_body
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Replace HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    # Clean up whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


def send_email(report_from, report_to, subject, html_body):
    """Send email via SES with both HTML and plain text for better deliverability."""
    logger.info(f"Attempting to send email from {report_from} to {report_to}")
    logger.info(f"Subject: {subject}")
    
    try:
        # Generate plain text version
        text_body = html_to_text(html_body)
        logger.info(f"Generated plain text version (length: {len(text_body)})")
        
        logger.info(f"SES client region: {ses.meta.region_name}")
        logger.info(f"Calling ses.send_email...")
        
        response = ses.send_email(
            Source=report_from,
            Destination={"ToAddresses": [report_to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                },
            },
        )
        message_id = response.get("MessageId", "unknown")
        logger.info(f"Email sent successfully to {report_to} - SES MessageId: {message_id}")
        put_metric("EmailSent", 1)
        return message_id
    except Exception as e:
        logger.error(f"Failed to send email: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        put_metric("EmailFailed", 1)
        raise


def lambda_handler(event, context):
    """Main Lambda handler."""
    try:
        # Fetch configuration from SSM
        cfg = get_params(
            [
                PARAM_REPORT_TO,
                PARAM_REPORT_FROM,
                PARAM_ARCHIVE_BUCKET,
                PARAM_TOP_N_SERVICES,
                PARAM_INCLUDE_MTD,
                PARAM_INCLUDE_DRIVERS,
            ]
        )

        report_to = cfg[PARAM_REPORT_TO]
        report_from = cfg[PARAM_REPORT_FROM]
        bucket = cfg[PARAM_ARCHIVE_BUCKET]
        top_n = int(cfg[PARAM_TOP_N_SERVICES])
        include_mtd = to_bool(cfg[PARAM_INCLUDE_MTD])
        include_drivers = to_bool(cfg[PARAM_INCLUDE_DRIVERS])

        now_local = datetime.now(TZ)
        end = now_local.date()  # exclusive end
        start = (now_local - timedelta(days=1)).date()  # yesterday
        date_label = start.isoformat()

        logger.info(f"Generating cost report for {date_label}")

        # Query yesterday's costs by service
        y_rows, y_total, y_raw = ce_grouped_cost(start, end, "SERVICE")
        put_metric("DailyTotalCost", y_total, "None")

        # Month-to-date
        mtd_rows = []
        mtd_total = 0.0
        mtd_raw = None
        if include_mtd:
            mtd_start = start.replace(day=1)
            mtd_rows, mtd_total, mtd_raw = ce_grouped_cost(mtd_start, end, "SERVICE")
            put_metric("MTDTotalCost", mtd_total, "None")

        # Drivers: usage types (overall yesterday)
        d_rows = []
        d_total = 0.0
        d_raw = None
        if include_drivers:
            d_rows, d_total, d_raw = ce_grouped_cost(start, end, "USAGE_TYPE")

        # Write artifacts to S3
        prefix = f"reports/{start.year}/{start.month:02d}/{start.day:02d}/"
        put_s3(
            bucket,
            prefix + "daily_by_service.json",
            json.dumps(y_raw).encode("utf-8"),
            "application/json",
        )
        put_s3(
            bucket,
            prefix + "daily_by_service.csv",
            csv_bytes(["service", "amount_usd"], y_rows),
            "text/csv",
        )

        if include_mtd and mtd_raw is not None:
            put_s3(
                bucket,
                prefix + "mtd_by_service.json",
                json.dumps(mtd_raw).encode("utf-8"),
                "application/json",
            )
            put_s3(
                bucket,
                prefix + "mtd_by_service.csv",
                csv_bytes(["service", "amount_usd"], mtd_rows),
                "text/csv",
            )

        if include_drivers and d_raw is not None:
            put_s3(
                bucket,
                prefix + "daily_drivers_usage_type.json",
                json.dumps(d_raw).encode("utf-8"),
                "application/json",
            )
            put_s3(
                bucket,
                prefix + "daily_drivers_usage_type.csv",
                csv_bytes(["usage_type", "amount_usd"], d_rows),
                "text/csv",
            )

        # Build email HTML
        html = f"""
    <html><body style="font-family: Arial, sans-serif;">
      <h2 style="margin:0 0 6px 0;">AWS Cost Report</h2>
      <div style="margin:0 0 12px 0;">Date (yesterday): <b>{date_label}</b></div>
      {html_table("Yesterday by service (top {top_n})", y_rows[:top_n], y_total)}
    """

        if include_mtd:
            html += html_table(f"Month-to-date by service (top {top_n})", mtd_rows[:top_n], mtd_total)

        if include_drivers:
            html += html_table(f"Yesterday drivers by usage type (top {top_n})", d_rows[:top_n], d_total)

        html += f"""
      <p style="margin-top:16px;">
        Archive: <b>s3://{bucket}/{prefix}</b>
      </p>
    </body></html>
    """

        # Use simple ASCII subject to avoid encoding issues
        subject = f"AWS Cost Report - {date_label} (daily by service)"

        # Send email
        logger.info(f"About to send email. From: {report_from}, To: {report_to}, Subject: {subject}")
        message_id = send_email(report_from, report_to, subject, html)
        logger.info(f"Email sending completed. MessageId: {message_id}")

        # Emit success metric
        put_metric("ReportGenerated", 1)

        result = {
            "ok": True,
            "date": date_label,
            "daily_total": y_total,
            "mtd_total": mtd_total if include_mtd else None,
        }

        logger.info(f"Report generated successfully: {result}")
        return result

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        put_metric("ReportFailed", 1)
        raise

