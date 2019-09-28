import json
# import requests
import cgi
from io import BytesIO

def get_boundary(header):
    '''Expect a string similar to 
    "multipart/form-data; boundary=---------------------------89421926422648", 
    we want to extract everythin afte the "="'''

    return header[header.find('=')+1:len(header)]


def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format

        Event doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict

        Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """

    # try:
    #     ip = requests.get("http://checkip.amazonaws.com/")
    # except requests.RequestException as e:
    #     # Send some context about this error to Lambda Logs
    #     print(e)

    #     raise e

    # print(event['body'])
    boundary = get_boundary(event['headers']['Content-Type'])

    print(boundary)

    # pdict = {'boundary': boundary}
    # data = cgi.parse_multipart(event['body'], pdict)

    f = open(event['body'], "rb", buffering=0)

    form = cgi.FieldStorage(f) 
    form.getfirst('text')


    # form = cgi.parse(
    #     fp=event['body'])
    # headers=event['headers'])

    print(form)


    return {
        "statusCode": 200,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps({
            "message": "hola mundo, hallo Welt",
            # "location": ip.text.replace("\n", "")
        }),
    }
