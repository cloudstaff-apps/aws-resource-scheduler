# AWS Resource Scheduler

[![Build Status](https://github.com/cloudstaff-apps/aws-resource-scheduler/actions/workflows/pip_publish.yml/badge.svg)](https://github.com/cloudstaff-apps/aws-resource-scheduler/actions/workflows/pip_publish.yml)
[![Latest Release](https://img.shields.io/github/v/release/cloudstaff-apps/aws-resource-scheduler?style=flat-square)](https://github.com/cloudstaff-apps/aws-resource-scheduler/releases/latest)
[![PyPI Latest Release](https://img.shields.io/pypi/v/aws-resource-scheduler?style=flat-square)](https://pypi.org/project/aws-resource-scheduler/)

AWS Resource Scheduler is an open-source Python module that automates the start and stop operations for various AWS resources, including EC2 instances, Auto Scaling Groups (ASG), ECS services, RDS databases, and Aurora clusters.

## Features

- Create a bundle of resources using names or tags that need to be started or stopped for a project or team.
- Combine resources from multiple regions or accounts.
- The application checks for resources to become healthy before moving to the next resource, allowing you to decide the sequence and dependency of resources.
- Doesn't require any changes to Tags or infrastructure, making it compatible with resources managed by IaC tools like CDK or Terraform.
- Start and stop AWS resources like EC2 instances, RDS databases, Aurora clusters.
- Scale up and down Auto Scaling Groups and ECS services.
- Schedule operations based on predefined configurations.
- Send notifications to Google Chat, Slack, or Microsoft Teams.

## Installation

```bash
pip install aws-resource-scheduler
```

### Configuration

Create a configuration like below, based on your need. 
You can keep more then workload in the same file an decide which one to use for the action. 

```yaml
workspaces:
  stage:
    aws_region: us-west-2
    role_arn: arn:aws:iam::123456789012:role/SchedulerRole
    storage:
      method: parameter_store  # Options: 'parameter_store' or 'dynamodb' to store last min,max,desire value for ecs and asg
      dynamodb_table: 'ResourceSchedulerTable'  # Required if method is 'dynamodb'
    notification:
      enable: true
      platform: google
      webhook_url: https://chat.googleapis.com/v1/spaces/XXX/messages?key=YYY&token=ZZZ
    ec2:
      name:
      - instance1
      - instance2
      tags:
        Environment: development
    asg:
      name:
      - asg1
      - asg2
    ecs:
      my-cluster:
      - service2
        services:
         - service1
       tags:
         name: service2
    rds:
      name:
      - db-instance1
      - db-instance2
    aurora:
      name: 
      - aurora-cluster1
      tags:
        Environment: development
```
Use service like YAML Checker <https://yamlchecker.com> to validate your yml config. Also use the status action to make sure that you are targeting correct resource with tags config.

### Arguments
-f, --filename: The configuration file
-w, --workspace: The workspace to use from the config file
-r, --resource: Comma-separated list of AWS resources (e.g., ec2, rds, asg, ecs, aurora)
-a, --action: The action to perform (start, stop, status)
-n, --no-wait: Do not wait for resources to reach desired state after starting or stopping
-t, --threads: Number of threads to use for parallel operations (default: 10)

### Example Usage
To stop EC2 instances, ASG, and ECS services in the stage workspace:
```bash
aws-resource-scheduler -f config-stage.yml -w stage -r ec2,rds,asg,ecs -a stop
```

To start EC2 instances, ASG, and ECS services:
```bash
aws-resource-scheduler -f config-stage.yml -w stage -r ec2,asg,ecs -a start
```

### IAM Role and Permission

To securely interact with AWS resources, create an IAM role with the necessary permissions listed below:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "SSMDescribeParameters",
            "Effect": "Allow",
            "Action": [
                "ssm:DescribeParameters"
            ],
            "Resource": "*"
        },
        {
            "Sid": "SSMGetPutParameters",
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter",
                "ssm:PutParameter"
            ],
            "Resource": "arn:aws:ssm:*:*:parameter/scheduler/*"
        },
        {
            "Sid": "EC2DescribeInstances",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeTags"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EC2StartStopInstances",
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "ec2:StopInstances"
            ],
            "Resource": "*"
        },
        {
            "Sid": "RDSDescribeInstances",
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBInstances",
                "rds:ListTagsForResource"
            ],
            "Resource": "*"
        },
        {
            "Sid": "RDSStartStopInstances",
            "Effect": "Allow",
            "Action": [
                "rds:StartDBInstance",
                "rds:StopDBInstance"
            ],
            "Resource": "arn:aws:rds:*:*:db:*"
        },
        {
            "Sid": "RDSDescribeClusters",
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBClusters",
                "rds:ListTagsForResource"
            ],
            "Resource": "*"
        },
        {
            "Sid": "RDSStartStopClusters",
            "Effect": "Allow",
            "Action": [
                "rds:StartDBCluster",
                "rds:StopDBCluster"
            ],
            "Resource": "arn:aws:rds:*:*:cluster:*"
        },
        {
            "Sid": "AutoScalingDescribe",
            "Effect": "Allow",
            "Action": [
                "autoscaling:DescribeAutoScalingGroups",
                "application-autoscaling:DescribeScalableTargets",
                "application-autoscaling:RegisterScalableTarget",
                "application-autoscaling:DeregisterScalableTarget",
                "application-autoscaling:DescribeScalingPolicies",
                "application-autoscaling:PutScalingPolicy"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AutoScalingUpdateGroups",
            "Effect": "Allow",
            "Action": [
                "autoscaling:UpdateAutoScalingGroup"
            ],
            "Resource": "arn:aws:autoscaling:*:*:autoScalingGroup:*:autoScalingGroupName/*"
        },
        {
            "Sid": "ECSDescribeServices",
            "Effect": "Allow",
            "Action": [
                "ecs:DescribeServices",
                "ecs:ListTagsForResource",
                "ecs:ListServices"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ECSUpdateServices",
            "Effect": "Allow",
            "Action": [
                "ecs:UpdateService"
            ],
            "Resource": "arn:aws:ecs:*:*:service/*"
        },
        {
          "Sid": "DynamodbStorage",
          "Effect": "Allow",
          "Action": [
            "dynamodb:PutItem",
            "dynamodb:GetItem",
            "dynamodb:UpdateItem"
          ],
        "Resource": "arn:aws:dynamodb:*:*:table/ResourceSchedulerTable"
        }
    ]
}
```

You can use Start and stop actions are allowed only on instances tagged with scheduler=true.
Other Services (RDS, Auto Scaling Groups, ECS): Similar tag-based restrictions are applied.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "EC2StartStopInstances",
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "ec2:StopInstances"
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "ec2:ResourceTag/scheduler": "true"
                }
            }
        }
    ]
}
```