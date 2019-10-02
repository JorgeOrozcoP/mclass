# Deep Learning Masterclass 1



## Introduction

This repository contains the code for thefinal deliverable of the Deep Learning Masterclass 1 Hildesheim Universität. It was built using the [fastai tutorial for AWS deployment](https://course.fast.ai/deployment_aws_lambda.html) and the [AWS tutorial on SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-getting-started-hello-world.html)


## Repository structure

The repository contains the following folders:

- **front-end**: contains a working example of a web-client built with Bootstrap.
- **obj-detector**: code of the object detector project. NOTE: up until 01-10-2019, the code only work in a local environment (Docker Desktop for Windows)
- **sam-app-backup**: some failed experiments on the implementation of the project
- **sam-app**: working example of a web service using AWS SAM. receives an encoded base64 image and returns the that same image flipped 90 degrees

## Build instructions

### sam-app

To build the project *sam-app*, clone the repo and move to that folder

```cd sam-app```

Then run the following commands

```sam build```

```sam package --output-template packaged.yaml --s3-bucket {NAME OF YOUR AWS BUCKET}}```

```sam deploy --template-file packaged.yaml --region {REGION TO DEPLOY} --capabilities CAPABILITY_IAM --stack-name aws-sam-getting-started```

### obj-detector
NOTE: the deployment only worked for local testing

```cd sam-app```

```sam build --use-container```

```sam package --output-template packaged.yaml --s3-bucket {NAME OF YOUR AWS BUCKET}}```

Test locally

```sam local start-api```

Following comand throws an error
```sam deploy --template-file packaged.yaml --region {REGION TO DEPLOY} --capabilities CAPABILITY_IAM --stack-name pytorch-sam-app```