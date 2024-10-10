## FAQ for AWS Resource Scheduler
Based on the common issues, available solutions, and user concerns with AWS resource scheduling tools like Lambda-based solutions, AWS Systems Manager Quick Setup, and other methods, here's a detailed FAQ for the AWS Resource Scheduler module:

1. Why not make scheduling part of Infrastructure as Code (IaC) using tools like Terraform or CDK?
Answer: Integrating scheduling directly into IaC tools like Terraform or CDK can make your setup rigid, especially when schedules need frequent changes. AWS Resource Scheduler decouples the scheduling logic from your core infrastructure, allowing you to modify start/stop schedules without needing to redeploy the entire infrastructure. This flexibility is essential for scenarios like changing business hours or project needs, where start/stop schedules need to adapt quickly.

2. How is AWS Resource Scheduler different from using AWS Lambda functions with tags?
Answer: Lambda functions can be configured to start/stop instances based on tags, but this typically requires you to write custom scripts and manage the invocation frequency, such as through CloudWatch Events​(Amazon Web Services, Inc.). AWS Resource Scheduler provides a more user-friendly, centralized configuration using YAML files and can manage multiple AWS services (e.g., EC2, RDS, ECS) across regions and accounts with a unified approach. It abstracts the scripting and maintenance of the Lambda logic.

3. How does AWS Resource Scheduler compare to AWS Systems Manager Quick Setup?
Answer: AWS Systems Manager Quick Setup is an easy way to set up schedules for EC2 instances based on tags​(Amazon AWS Docs). However, it is limited primarily to EC2 and focuses on simple start/stop actions. AWS Resource Scheduler offers broader resource management capabilities, such as handling ASG scaling, ECS service updates, and Aurora clusters. Additionally, it supports complex dependencies between resources, making it suitable for environments where multiple services need coordinated actions.

4. Why not just use a Lambda function for scheduling?
Answer: While Lambda functions are a good option for lightweight, custom automation, they can become complex to manage when you need to coordinate multiple services or manage configurations across different environments. AWS Resource Scheduler handles these complexities by offering a structured way to manage schedules, including configuration files and support for both SSM Parameter Store and DynamoDB for storing state information.

5. Can AWS Resource Scheduler manage resources across multiple AWS accounts?
Answer: Yes, AWS Resource Scheduler can manage resources across multiple accounts by leveraging AWS IAM roles for cross-account access. This allows a centralized scheduler to control resources in various accounts without needing individual scripts or Lambda functions in each account.

6. How does it handle the startup sequence of resources with dependencies?
Answer: AWS Resource Scheduler checks the health and readiness of each resource before proceeding to the next. For example, if an RDS database must be available before starting an application hosted on EC2, the scheduler ensures this sequence is respected. This is more efficient than simple tag-based or Lambda solutions, which may require custom logic for such dependencies.

7. What if I already have scripts for starting/stopping instances, why should I switch?
Answer: Custom scripts can be difficult to maintain as the environment grows. AWS Resource Scheduler offers a more maintainable solution by using a configuration-based approach, allowing you to change settings without modifying code. It also provides logging and error handling out of the box, making troubleshooting simpler.
8. Can AWS Resource Scheduler be used in a serverless setup?

Answer: Yes, AWS Resource Scheduler can run from AWS Lambda when packaged into a zip file, allowing you to execute the scheduling logic without maintaining servers. This setup can reduce costs and simplifies deployment, while still benefiting from the centralized configuration.

9. How does AWS Resource Scheduler handle configuration changes?
Answer: Configuration changes can be made directly to the YAML file or by using a versioned configuration stored in an S3 bucket. This flexibility makes it easy to update schedules without needing code changes or redeployments. For example, changing business hours can be done by editing the ci/cd pipeline, cron job or event.

10. Why use DynamoDB instead of Parameter Store for storing state information?
Answer: Parameter Store is suitable for smaller environments where you don't need to manage a large number of records or perform complex queries. DynamoDB, on the other hand, is ideal for scaling to thousands of resources and offers more control over data access patterns. Using DynamoDB allows for centralized state storage, making it possible to manage the scheduler across multiple AWS accounts without replicating configuration data in each account.