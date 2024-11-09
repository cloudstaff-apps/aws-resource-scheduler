# AWS Resource Scheduler Lambda Deployment

[![Build Status](https://github.com/cloudstaff-apps/aws-resource-scheduler/actions/workflows/build_lambda_package.yml/badge.svg)](https://github.com/cloudstaff-apps/aws-resource-scheduler/actions/workflows/build_lambda_package.yml)
[![Latest Release](https://img.shields.io/github/v/release/cloudstaff-apps/aws-resource-scheduler?style=flat-square)](https://github.com/cloudstaff-apps/aws-resource-scheduler/releases/latest)
[![PyPI Latest Release](https://img.shields.io/pypi/v/aws-resource-scheduler?style=flat-square)](https://pypi.org/project/aws-resource-scheduler/)

This Lambda function package allows you to deploy and execute the `aws-resource-scheduler` on AWS Lambda.

## Setup Instructions

1. **Deployment Package**: Download the latest [`aws_resource_scheduler_lambda_package.zip`](https://github.com/cloudstaff-apps/aws-resource-scheduler/releases/latest/download/aws_resource_scheduler_lambda_package.zip) from the GitHub release.

2. **Upload to AWS Lambda**:
   - Go to the AWS Lambda Console.
   - Create a new Lambda function (e.g., `aws-resource-scheduler`).
   - Choose Python 3.12 runtime.
   - Upload the `aws_resource_scheduler_lambda_package.zip` file as the Lambda code.
   - Set the handler to `lambda_function.lambda_handler`.

3. **Environment Variables**:
   - `CONFIG_FILE`: Path to the config file included in the Lambda package (e.g., `example/config-default-tags.yml`).
   - `CONFIG_S3_BUCKET`: (Optional) S3 bucket name for configuration.
   - `CONFIG_S3_KEY`: (Optional) Key within S3 bucket to fetch configuration from.
   - `WORKSPACE`: Workspace name (e.g., `stage`).
   - `RESOURCES`: Comma-separated list of resources to manage (e.g., `ec2,rds,asg,ecs,aurora`).
   - `ACTION`: Action to perform (`start`, `stop`, `status`).
   - `NO_WAIT`: Set to `true` or `false` (default: `false`).
   - `THREADS`: Number of threads for execution (default: `10`).
   - `LOG_LEVEL`: Logging level (e.g., `INFO`, `DEBUG`).

4. **Configuration Options**:
   - You can use the default `config-default-tags.yml` included in the package or fetch the configuration file dynamically from S3 by setting `CONFIG_S3_BUCKET` and `CONFIG_S3_KEY`.
   - Alternatively, create a local `config.yml` file and add it to the Lambda package using:
     ```bash
     zip -u aws_resource_scheduler_lambda_package.zip config.yml
     ```
     
5. **CloudWatch Event Trigger**:
   - Set up a CloudWatch Event rule to trigger the Lambda function on a schedule, such as every hour or daily, depending on your needs.

6. **Testing**:
   - Create a test event in the AWS Lambda Console:
     ```json
     {
       "config_file": "example/config-default-tags.yml",
       "workspace": "stage",
       "resources": "ec2,rds,asg,aurora",
       "action": "status",
       "no_wait": true,
       "threads": 10
     }
     ```
   - Invoke the function and check CloudWatch Logs for the output.

## Permissions

Ensure the Lambda function role has the necessary permissions assume role that are configured in the config:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole"
      ],
      "Resource": "arn:aws:iam::123456789012:role/SchedulerRole"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

And the role should allow lambda to assume

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Statement1",
            "Effect": "Allow",
            "Principal": {
                "AWS": [
                    "arn:aws:sts::123456789012:assumed-role/aws_resource_scheduler-role-nxnytew9/aws_resource_scheduler"
                ]
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

## Notes

- If your configuration file changes frequently, using S3 for config storage is recommended.
- Make sure to adjust the IAM role permissions to the principle of least privilege.
