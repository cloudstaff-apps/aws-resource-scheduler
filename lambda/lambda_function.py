# lambda_function.py
import logging
import json
import os
import boto3
from aws_resource_scheduler.scheduler import main as scheduler_main

# Explicitly set the root logger level
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

def lambda_handler(event, context):
    logging.info("Lambda handler started with log level: %s", log_level)
    # Set up parameters
    config_file = os.environ.get('CONFIG_FILE', 'example/config-default-tags.yml')
    s3_bucket = os.environ.get('CONFIG_S3_BUCKET')
    s3_key = os.environ.get('CONFIG_S3_KEY')

    if s3_bucket and s3_key:
        # Fetch config from S3
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        config_content = response['Body'].read().decode('utf-8')
        with open('/tmp/config.yml', 'w') as f:
            f.write(config_content)
        config_file = '/tmp/config.yml'

    # Get parameters from event or environment variables
    config_file = os.environ.get('CONFIG_FILE', 'config.yml')
    workspace = os.environ.get('WORKSPACE', 'default')
    resources = os.environ.get('RESOURCES', 'ec2,rds,asg,ecs,aurora')
    action = os.environ.get('ACTION', 'status')
    no_wait = os.environ.get('NO_WAIT', 'true').lower() == 'true'
    threads = int(os.environ.get('THREADS', '10'))

    # If parameters are provided in the event, they override environment variables
    config_file = event.get('config_file', config_file)
    workspace = event.get('workspace', workspace)
    resources = event.get('resources', resources)
    action = event.get('action', action)
    no_wait = event.get('no_wait', no_wait)
    threads = event.get('threads', threads)

    # Prepare arguments for the scheduler
    class Args:
        pass

    args = Args()
    args.file = config_file
    args.workspace = workspace
    args.resource = resources
    args.action = action
    args.no_wait = no_wait
    args.threads = threads

    # Run the scheduler
    try:
        scheduler_main(args)
        return {
            'statusCode': 200,
            'body': json.dumps('Scheduler executed successfully.')
        }
    except Exception as e:
        logging.exception(f"An error occurred: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"An error occurred: {str(e)}")
        }
