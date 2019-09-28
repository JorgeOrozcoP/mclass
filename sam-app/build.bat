echo off

sam build
sam package --output-template packaged.yaml --s3-bucket objdetection-orozcobusch
sam deploy --template-file packaged.yaml --region eu-central-1 --capabilities CAPABILITY_IAM --stack-name aws-sam-getting-started
aws cloudformation describe-stacks --stack-name aws-sam-getting-started --region eu-central-1 --query "Stacks[].Outputs"