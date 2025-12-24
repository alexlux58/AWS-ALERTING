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
budgets = boto3.client("budgets", region_name=CE_REGION)

PARAM_REPORT_TO = os.environ["PARAM_REPORT_TO"]
PARAM_REPORT_FROM = os.environ["PARAM_REPORT_FROM"]
PARAM_ARCHIVE_BUCKET = os.environ["PARAM_ARCHIVE_BUCKET"]
PARAM_TOP_N_SERVICES = os.environ["PARAM_TOP_N_SERVICES"]
PARAM_INCLUDE_MTD = os.environ["PARAM_INCLUDE_MTD"]
PARAM_INCLUDE_DRIVERS = os.environ["PARAM_INCLUDE_DRIVERS"]

ENABLE_METRICS = os.environ.get("ENABLE_METRICS", "true").lower() == "true"
METRICS_NAMESPACE = os.environ.get("METRICS_NAMESPACE", "cost-alerting")
BUDGET_NAME = os.environ.get("BUDGET_NAME", "cost-alerting-monthly")

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


def ce_grouped_cost(start: date, end: date, group_key: str, aggregate_days=True):
    """
    Query Cost Explorer grouped by dimension.
    If aggregate_days=True, sums costs across all days in the period.
    If aggregate_days=False, only returns the first day (for daily reports).
    """
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": group_key}],
        )
        
        # Aggregate costs across all days if requested
        if aggregate_days:
            # Sum costs across all days in ResultsByTime
            aggregated = {}
            for result in resp["ResultsByTime"]:
                groups = result.get("Groups", [])
                for g in groups:
                    key = g["Keys"][0]
                    amt = money(g["Metrics"]["UnblendedCost"]["Amount"])
                    if key not in aggregated:
                        aggregated[key] = 0.0
                    aggregated[key] += amt
            # Convert to list of tuples and sort
            rows = [(k, v) for k, v in aggregated.items() if v > 0]
            rows.sort(key=lambda x: x[1], reverse=True)
            total = sum(v for _, v in rows)
        else:
            # For daily reports, only use the first day
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


def get_daily_totals(num_days: int, end_date: date):
    """Get daily cost totals for the past N days (for trend analysis)."""
    try:
        start_date = end_date - timedelta(days=num_days)
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
        
        daily_costs = []
        for result in resp["ResultsByTime"]:
            day_start = result["TimePeriod"]["Start"]
            total = money(result.get("Total", {}).get("UnblendedCost", {}).get("Amount", "0"))
            daily_costs.append({"date": day_start, "cost": total})
        
        return daily_costs
    except Exception as e:
        logger.warning(f"Failed to get daily totals: {e}")
        return []


def get_regional_breakdown(start: date, end: date):
    """Get cost breakdown by AWS region."""
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "REGION"}],
        )
        
        aggregated = {}
        for result in resp["ResultsByTime"]:
            groups = result.get("Groups", [])
            for g in groups:
                region = g["Keys"][0]
                if not region or region == "global":
                    region = "Global"
                amt = money(g["Metrics"]["UnblendedCost"]["Amount"])
                if region not in aggregated:
                    aggregated[region] = 0.0
                aggregated[region] += amt
        
        rows = [(k, v) for k, v in aggregated.items() if v > 0.001]
        rows.sort(key=lambda x: x[1], reverse=True)
        total = sum(v for _, v in rows)
        return rows, total
    except Exception as e:
        logger.warning(f"Failed to get regional breakdown: {e}")
        return [], 0.0


def get_budget_status():
    """Get current budget status and utilization."""
    try:
        account_id = boto3.client("sts").get_caller_identity()["Account"]
        resp = budgets.describe_budget(
            AccountId=account_id,
            BudgetName=BUDGET_NAME,
        )
        budget = resp["Budget"]
        limit = float(budget["BudgetLimit"]["Amount"])
        
        # Get actual spend from CalculatedSpend
        actual = float(budget.get("CalculatedSpend", {}).get("ActualSpend", {}).get("Amount", "0"))
        forecasted = float(budget.get("CalculatedSpend", {}).get("ForecastedSpend", {}).get("Amount", "0"))
        
        utilization = (actual / limit * 100) if limit > 0 else 0
        
        return {
            "limit": limit,
            "actual": actual,
            "forecasted": forecasted,
            "utilization": utilization,
            "name": BUDGET_NAME,
        }
    except Exception as e:
        logger.warning(f"Failed to get budget status: {e}")
        return None


def get_cost_forecast(start: date, end: date):
    """Get AWS cost forecast for the period.
    Returns the forecasted total cost for the period (mean value).
    """
    try:
        resp = ce.get_cost_forecast(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Metric="UNBLENDED_COST",
            Granularity="MONTHLY",
        )
        # Cost Explorer forecast returns ForecastResultsByTime array
        # For monthly granularity, we typically get one result
        # Use MeanValue for the forecast
        if resp.get("ForecastResultsByTime"):
            # Sum all forecast periods (usually just one for monthly)
            total = 0.0
            for result in resp["ForecastResultsByTime"]:
                mean_value = result.get("MeanValue", {}).get("Amount", "0")
                total += money(mean_value)
            return total
        return 0.0
    except Exception as e:
        logger.warning(f"Failed to get cost forecast: {e}")
        return None


def calculate_change(current: float, previous: float):
    """Calculate percentage change between two values."""
    if previous == 0:
        if current == 0:
            return 0, "→"
        return 100, "↑"
    
    change = ((current - previous) / previous) * 100
    if change > 5:
        arrow = "↑"
    elif change < -5:
        arrow = "↓"
    else:
        arrow = "→"
    
    return change, arrow


def generate_sparkline(daily_costs):
    """Generate a simple ASCII/Unicode sparkline from daily costs."""
    if not daily_costs or len(daily_costs) < 2:
        return ""
    
    values = [d["cost"] for d in daily_costs]
    min_val = min(values)
    max_val = max(values)
    
    if max_val == min_val:
        return "▁" * len(values)
    
    # Unicode block characters for sparkline
    blocks = "▁▂▃▄▅▆▇█"
    
    sparkline = ""
    for v in values:
        # Normalize to 0-7 range
        normalized = int((v - min_val) / (max_val - min_val) * 7)
        sparkline += blocks[normalized]
    
    return sparkline


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


def html_table(title, rows, total, show_percentage=True, filter_zeros=True):
    """Generate HTML table for email with improved formatting."""
    # Filter out zero-cost items if requested
    if filter_zeros:
        rows = [(k, v) for k, v in rows if v > 0.001]  # Use 0.001 to handle floating point precision
    
    if not rows:
        return f"""
      <h3 style="margin:16px 0 8px 0;">{title}</h3>
      <p style="color:#666;font-style:italic;">No charges for this period.</p>
    """
    
    # Build table rows with percentage if total > 0
    trs = []
    for k, v in rows:
        percentage = f"{(v/total*100):.1f}%" if total > 0 and show_percentage else ""
        percentage_cell = f"<td style='padding:6px 10px;border:1px solid #ddd;text-align:right;color:#666;font-size:0.9em'>{percentage}</td>" if show_percentage else ""
        trs.append(
            f"<tr>"
            f"<td style='padding:6px 10px;border:1px solid #ddd'>{k}</td>"
            f"<td style='padding:6px 10px;border:1px solid #ddd;text-align:right;font-weight:500'>${v:,.2f}</td>"
            f"{percentage_cell}"
            f"</tr>"
        )
    
    trs_str = "\n".join(trs)
    
    # Build header
    header_cols = "<th style='padding:6px 10px;border:1px solid #ddd;text-align:left;background-color:#f5f5f5'>Service</th><th style='padding:6px 10px;border:1px solid #ddd;text-align:right;background-color:#f5f5f5'>Amount</th>"
    if show_percentage and total > 0:
        header_cols += "<th style='padding:6px 10px;border:1px solid #ddd;text-align:right;background-color:#f5f5f5'>% of Total</th>"
    
    return f"""
      <h3 style="margin:16px 0 8px 0;color:#333;">{title}</h3>
      <table style="border-collapse:collapse;width:100%;margin-bottom:16px;">
        <thead>
          <tr>
            {header_cols}
          </tr>
        </thead>
        <tbody>
          {trs_str}
          <tr style="background-color:#f9f9f9;border-top:2px solid #333;">
            <td style="padding:8px 10px;border:1px solid #ddd;"><b>Total</b></td>
            <td style="padding:8px 10px;border:1px solid #ddd;text-align:right;"><b>${total:,.2f}</b></td>
            {f"<td style='padding:8px 10px;border:1px solid #ddd;text-align:right'><b>100.0%</b></td>" if show_percentage and total > 0 else ""}
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
        end = now_local.date()  # exclusive end (today)
        start = (now_local - timedelta(days=1)).date()  # yesterday
        date_label = start.isoformat()

        logger.info(f"Generating cost report for {date_label}")

        # Query yesterday's costs by service (single day, no aggregation)
        y_rows, y_total, y_raw = ce_grouped_cost(start, end, "SERVICE", aggregate_days=False)
        put_metric("DailyTotalCost", y_total, "None")

        # Get day-before-yesterday for comparison
        day_before = start - timedelta(days=1)
        prev_rows, prev_total, _ = ce_grouped_cost(day_before, start, "SERVICE", aggregate_days=False)
        dod_change, dod_arrow = calculate_change(y_total, prev_total)

        # Get same day last week for comparison
        week_ago = start - timedelta(days=7)
        week_ago_end = week_ago + timedelta(days=1)
        wow_rows, wow_total, _ = ce_grouped_cost(week_ago, week_ago_end, "SERVICE", aggregate_days=False)
        wow_change, wow_arrow = calculate_change(y_total, wow_total)

        # Get 7-day trend for sparkline
        daily_costs = get_daily_totals(7, end)
        sparkline = generate_sparkline(daily_costs)
        
        # Get regional breakdown
        regional_rows, regional_total = get_regional_breakdown(start, end)

        # Month-to-date (from first day of month through yesterday, inclusive)
        mtd_rows = []
        mtd_total = 0.0
        mtd_raw = None
        if include_mtd:
            mtd_start = start.replace(day=1)  # First day of the month
            mtd_rows, mtd_total, mtd_raw = ce_grouped_cost(mtd_start, end, "SERVICE", aggregate_days=True)
            put_metric("MTDTotalCost", mtd_total, "None")

        # Get budget status
        budget_info = get_budget_status()
        
        # Calculate first day of current month and first day of next month
        month_start = start.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1, day=1)
        else:
            next_month = start.replace(month=start.month + 1, day=1)
        
        # Get AWS cost forecast for the entire month (from month start to month end)
        # This gives us the total forecasted spend for the month
        aws_forecast = get_cost_forecast(month_start, next_month) if include_mtd else None

        # Drivers: usage types (overall yesterday, single day)
        d_rows = []
        d_total = 0.0
        d_raw = None
        if include_drivers:
            d_rows, d_total, d_raw = ce_grouped_cost(start, end, "USAGE_TYPE", aggregate_days=False)

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

        # Calculate daily average for context
        days_in_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        days_elapsed = start.day
        daily_avg = mtd_total / days_elapsed if days_elapsed > 0 and include_mtd else 0
        projected_monthly = daily_avg * days_in_month.day if include_mtd else 0
        
        # Format change indicators with color
        def format_change(change, arrow):
            if change > 5:
                color = "#dc3545"  # Red for increase
            elif change < -5:
                color = "#28a745"  # Green for decrease
            else:
                color = "#6c757d"  # Gray for stable
            return f'<span style="color:{color};font-weight:500">{arrow} {abs(change):.1f}%</span>'
        
        dod_formatted = format_change(dod_change, dod_arrow)
        wow_formatted = format_change(wow_change, wow_arrow)
        
        # Build budget progress bar HTML
        # Use MTD total from Cost Explorer for consistency, not Budgets API actual
        budget_html = ""
        if budget_info and include_mtd:
            # Use MTD total instead of Budgets API actual for consistency
            budget_actual = mtd_total
            budget_limit = budget_info["limit"]
            utilization = (budget_actual / budget_limit * 100) if budget_limit > 0 else 0
            
            # Use Cost Explorer forecast if available, otherwise fall back to Budgets forecast
            forecasted_spend = aws_forecast if aws_forecast is not None else budget_info.get("forecasted", 0)
            
            bar_color = "#28a745" if utilization < 80 else ("#ffc107" if utilization < 100 else "#dc3545")
            budget_html = f'''
            <div style="background: #f8f9fa; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 14px; font-weight: 600;">📊 Budget Status: {budget_info["name"]}</div>
                <div style="font-size: 14px; color: #666;">${budget_actual:,.2f} / ${budget_limit:,.2f}</div>
              </div>
              <div style="background: #e9ecef; border-radius: 4px; height: 20px; overflow: hidden;">
                <div style="background: {bar_color}; height: 100%; width: {min(utilization, 100):.1f}%; transition: width 0.3s;"></div>
              </div>
              <div style="display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: #666;">
                <div>{utilization:.1f}% used</div>
                <div>Forecasted (EOM): ${forecasted_spend:,.2f}</div>
              </div>
            </div>
            '''
        
        # Build regional breakdown HTML
        regional_html = ""
        if regional_rows:
            regional_items = "".join([
                f'<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #eee;"><span>{region}</span><span style="font-weight:500">${cost:,.2f}</span></div>'
                for region, cost in regional_rows[:5]  # Top 5 regions
            ])
            regional_html = f'''
            <div style="background: #f8f9fa; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
              <div style="font-size: 14px; font-weight: 600; margin-bottom: 12px;">🌎 Cost by Region (Yesterday)</div>
              {regional_items}
            </div>
            '''
        
        # Build 7-day trend HTML
        trend_html = ""
        if daily_costs and sparkline:
            min_cost = min(d["cost"] for d in daily_costs)
            max_cost = max(d["cost"] for d in daily_costs)
            avg_cost = sum(d["cost"] for d in daily_costs) / len(daily_costs)
            trend_html = f'''
            <div style="background: #f8f9fa; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
              <div style="font-size: 14px; font-weight: 600; margin-bottom: 8px;">📈 7-Day Trend</div>
              <div style="font-family: monospace; font-size: 24px; letter-spacing: 2px; color: #667eea; margin: 8px 0;">{sparkline}</div>
              <div style="display: flex; justify-content: space-between; font-size: 12px; color: #666;">
                <div>Min: ${min_cost:,.2f}</div>
                <div>Avg: ${avg_cost:,.2f}</div>
                <div>Max: ${max_cost:,.2f}</div>
              </div>
            </div>
            '''
        
        # Build email HTML with improved formatting
        html = f"""
    <html>
    <head>
      <meta charset="UTF-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
      <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; margin: -20px -20px 20px -20px;">
        <h1 style="margin: 0 0 8px 0; font-size: 24px;">☁️ AWS Cost Report</h1>
        <div style="font-size: 14px; opacity: 0.9;">Daily Report for <b>{date_label}</b> ({start.strftime('%A')})</div>
      </div>
      
      <!-- Summary Cards -->
      <div style="display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 20px;">
        <div style="flex: 1; min-width: 200px; background: #f8f9fa; padding: 16px; border-radius: 6px; border-left: 4px solid #667eea;">
          <div style="font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px;">Yesterday's Total</div>
          <div style="font-size: 28px; font-weight: bold; color: #333;">${y_total:,.2f}</div>
          <div style="font-size: 12px; margin-top: 4px;">
            vs. day before: {dod_formatted} &nbsp;|&nbsp; vs. week ago: {wow_formatted}
          </div>
        </div>
        {f'''
        <div style="flex: 1; min-width: 200px; background: #f8f9fa; padding: 16px; border-radius: 6px; border-left: 4px solid #764ba2;">
          <div style="font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px;">Month-to-Date ({days_elapsed} days)</div>
          <div style="font-size: 28px; font-weight: bold; color: #333;">${mtd_total:,.2f}</div>
          <div style="font-size: 12px; color: #666; margin-top: 4px;">
            Daily avg: ${daily_avg:,.2f} &nbsp;|&nbsp; Projected: ${projected_monthly:,.2f}
          </div>
        </div>
        ''' if include_mtd else ''}
      </div>
      
      <!-- Budget Progress -->
      {budget_html}
      
      <!-- 7-Day Trend -->
      {trend_html}
      
      <!-- Service Breakdown Tables -->
      {html_table(f"Yesterday by Service (Top {top_n})", y_rows[:top_n], y_total, show_percentage=True, filter_zeros=True)}
      
      {html_table(f"Month-to-Date by Service (Top {top_n})", mtd_rows[:top_n], mtd_total, show_percentage=True, filter_zeros=True) if include_mtd else ""}
      
      <!-- Regional Breakdown -->
      {regional_html}
      
      <!-- Cost Drivers -->
      {html_table(f"Cost Drivers - Usage Types (Top {top_n})", d_rows[:top_n], d_total, show_percentage=True, filter_zeros=True) if include_drivers else ""}
      
      <!-- Insights Section -->
      <div style="background: #e8f4f8; padding: 16px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #17a2b8;">
        <div style="font-size: 14px; font-weight: 600; margin-bottom: 8px;">💡 Quick Insights</div>
        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #555;">
          <li><b>Top cost driver:</b> {y_rows[0][0] if y_rows else 'N/A'} (${y_rows[0][1]:,.2f})</li>
          {f'<li><b>Day-over-day:</b> {"Increased" if dod_change > 5 else "Decreased" if dod_change < -5 else "Stable"} ({dod_arrow} {abs(dod_change):.1f}%)</li>' if prev_total > 0 else ''}
          {f'<li><b>Week-over-week:</b> {"Increased" if wow_change > 5 else "Decreased" if wow_change < -5 else "Stable"} ({wow_arrow} {abs(wow_change):.1f}%)</li>' if wow_total > 0 else ''}
          {f'<li><b>Budget utilization:</b> {(mtd_total / budget_info["limit"] * 100):.1f}% of ${budget_info["limit"]:,.2f} monthly budget (${mtd_total:,.2f} spent)</li>' if (budget_info and include_mtd) else ''}
          {f'<li><b>On track for:</b> ${projected_monthly:,.2f} this month (based on {days_elapsed}-day average)</li>' if include_mtd else ''}
        </ul>
      </div>
      
      <!-- Archive Location -->
      <div style="margin-top: 24px; padding: 16px; background: #f8f9fa; border-radius: 6px; font-size: 13px; color: #666;">
        <div style="margin-bottom: 8px;"><strong>📦 Archive Location:</strong></div>
        <div style="font-family: monospace; background: white; padding: 8px; border-radius: 4px; border: 1px solid #ddd; word-break: break-all;">s3://{bucket}/{prefix}</div>
        <div style="margin-top: 12px; font-size: 12px;">
          Reports archived in JSON and CSV formats for historical analysis.
        </div>
      </div>
      
      <!-- Footer -->
      <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999; text-align: center;">
        Generated by AWS Cost Alerting System • {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}
      </div>
    </body>
    </html>
    """

        # Use simple ASCII subject with quick summary
        change_indicator = dod_arrow if dod_change != 0 else ""
        subject = f"AWS Cost Report - {date_label}: ${y_total:,.2f} {change_indicator}"

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
            "dod_change": dod_change,
            "wow_change": wow_change,
        }

        logger.info(f"Report generated successfully: {result}")
        return result

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        put_metric("ReportFailed", 1)
        raise

