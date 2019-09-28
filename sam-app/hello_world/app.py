import json
import io
from PIL import Image
import base64

# import requests


def parse_encoded_string(enc_string):
    '''Input an encoded string similar to 
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD//gA7Q1JFQVRPU...", 
    extract everything after the ",". '''
    return enc_string[enc_string.find(',') + 1:len(enc_string)]


def get_input(event):
    '''get input from event'''

    # encoded base64 image
    # form https://stackoverflow.com/questions/2323128/convert-string-in-base64
    # -to-image-and-save-on-filesystem-in-python 

    encoded_img = parse_encoded_string(event['body'])

    decoded = base64.b64decode(encoded_img)
    img = Image.open(io.BytesIO(decoded))

    return img


def analyze(img):
    '''Run main algorithm'''

    # width, height = img.size

    img = img.rotate(90)

    return img


def get_output(img):
    '''input a PIL loaded image, return an encoded base64 string
    ready for html parsing'''

    # from: https://stackoverflow.com/questions/48229318/
    # how-to-convert-image-pil-into-base64-without-saving?rq=1

    header = 'data:image/jpeg;base64,'

    buff = io.BytesIO()
    img.save(buff,format="JPEG")

    return header + base64.b64encode(buff.getvalue()).decode('UTF-8')


def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format
        assert(event.keys() == ['httpMethod', 'body', 'resource', 
        'requestContext', 'queryStringParameters', 
        'multiValueQueryStringParameters', 'headers', 'multiValueHeaders', 
        'pathParameters', 'stageVariables', 'path', 'isBase64Encoded'])

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

    # see the input
    # print('---------Body and Keys---------')
    # print(event['body'])
    # print(list(event.keys()))

    img = get_input(event)

    processed_img = analyze(img)

    enc_img = get_output(processed_img)


    return {
        "statusCode": 200,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps({
            "message": "hola mundo, hallo Welt",
            "enc_img": enc_img,
        }),
    }
