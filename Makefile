.PHONY: init plan apply destroy validate test clean format

# Terraform directory
TF_DIR = infra

# Initialize Terraform
init:
	cd $(TF_DIR) && terraform init

# Plan Terraform changes
plan:
	cd $(TF_DIR) && terraform plan

# Apply Terraform changes
apply:
	cd $(TF_DIR) && terraform apply

# Destroy infrastructure
destroy:
	cd $(TF_DIR) && terraform destroy

# Validate Terraform configuration
validate:
	cd $(TF_DIR) && terraform validate
	cd $(TF_DIR) && terraform fmt -check

# Format Terraform code
format:
	cd $(TF_DIR) && terraform fmt -recursive

# Test Lambda function (requires AWS credentials)
test:
	@echo "Testing reporter Lambda..."
	aws lambda invoke \
		--function-name cost-alerting-reporter \
		--payload '{}' \
		/tmp/cost-report-test.json && \
	cat /tmp/cost-report-test.json && \
	rm /tmp/cost-report-test.json

# Test remediation Lambda
test-remediation:
	@echo "Testing remediation Lambda..."
	aws lambda invoke \
		--function-name cost-alerting-remediation \
		--payload '{}' \
		/tmp/remediation-test.json && \
	cat /tmp/remediation-test.json && \
	rm /tmp/remediation-test.json

# Check S3 archive
check-archive:
	@echo "Checking S3 archive..."
	@BUCKET=$$(cd $(TF_DIR) && terraform output -raw archive_bucket); \
	aws s3 ls s3://$$BUCKET/reports/ --recursive | tail -20

# View Lambda logs
logs:
	@echo "Tailing Lambda logs (Ctrl+C to exit)..."
	aws logs tail /aws/lambda/cost-alerting-reporter --follow

# View remediation Lambda logs
logs-remediation:
	@echo "Tailing remediation Lambda logs (Ctrl+C to exit)..."
	aws logs tail /aws/lambda/cost-alerting-remediation --follow

# Clean build artifacts
clean:
	rm -rf $(TF_DIR)/.build/
	rm -rf lambda/__pycache__/
	rm -rf cost_remediation_lambda/__pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

# Install Lambda dependencies
install-deps:
	cd lambda && pip install -r requirements.txt -t .
	cd cost_remediation_lambda && pip install -r requirements.txt -t .

# Full validation
full-validate: validate
	@echo "Running full validation..."
	@python3 -m py_compile lambda/app.py || echo "Python syntax check failed"
	@python3 -m py_compile cost_remediation_lambda/app.py || echo "Python syntax check failed"

# Help
help:
	@echo "Available targets:"
	@echo "  init              - Initialize Terraform"
	@echo "  plan              - Plan Terraform changes"
	@echo "  apply             - Apply Terraform changes"
	@echo "  destroy           - Destroy infrastructure"
	@echo "  validate          - Validate Terraform configuration"
	@echo "  format            - Format Terraform code"
	@echo "  test              - Test reporter Lambda"
	@echo "  test-remediation  - Test remediation Lambda"
	@echo "  check-archive     - Check S3 archive contents"
	@echo "  logs              - View reporter Lambda logs"
	@echo "  logs-remediation  - View remediation Lambda logs"
	@echo "  clean             - Clean build artifacts"
	@echo "  install-deps      - Install Lambda dependencies"
	@echo "  full-validate     - Run all validation checks"
	@echo "  help              - Show this help message"

