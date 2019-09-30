# this import statement is needed if you want to use the AWS Lambda Layer called "pytorch-v1-py36"
# it unzips all of the pytorch & dependency packages when the script is loaded to avoid the 250 MB unpacked limit in AWS Lambda
try:
    import unzip_requirements
except ImportError:
    pass

import os
import io
import json
import tarfile
import glob
import time
import logging
import base64

import boto3
import requests
from PIL import Image

import torch
import torch.nn.functional as F
from torchvision import models, transforms



# our library
from RetinaNetAndAuxillaries import *

from fastai.vision import load_learner


# load the S3 client when lambda execution context is created
s3 = boto3.client('s3')

# classes for the image classification
classes = []

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# get bucket name from ENV variable
MODEL_BUCKET=os.environ.get('MODEL_BUCKET')
logger.info(f'Model Bucket is {MODEL_BUCKET}')

# get bucket prefix from ENV variable
MODEL_KEY=os.environ.get('MODEL_KEY')
logger.info(f'Model Prefix is {MODEL_KEY}')

# un-comment (maybe) for preprocessing
# processing pipeline to resize, normalize and create tensor object
# preprocess = transforms.Compose([
#     transforms.Resize(256),
#     transforms.CenterCrop(224),
#     transforms.ToTensor(),
#     transforms.Normalize(
#         mean=[0.485, 0.456, 0.406],
#         std=[0.229, 0.224, 0.225]
#     )
# ])

# un-comment for production

def load_model():
    """Loads the PyTorch model into memory from a file on S3.

    Returns
    ------
    Vision model: Module
        Returns the vision PyTorch model to use for inference.

    """      
    global classes
    logger.info('Loading model from S3')
    obj = s3.get_object(Bucket=MODEL_BUCKET, Key=MODEL_KEY)
    # bytestream = io.BytesIO(obj['Body'].read())

    print(obj.keys())



    # learn = load_learner(file=io.BytesIO(img_request.content).read())

    # learn = load_learner(path=MODELS, file='stage2-256.pkl')


# =======>> uncomment fo production

# load the model when lambda execution context is created
# model = load_model()


def predict(input_object, model):
    """Predicts the class from an input image.

    Parameters
    ----------
    input_object: Tensor, required
        The tensor object containing the image pixels reshaped and normalized.

    Returns
    ------
    Response object: dict
        Returns the predicted class and confidence score.

    """        
    logger.info("Calling prediction on model")
    start_time = time.time()
    predict_values = model(input_object)
    logger.info("--- Inference time: %s seconds ---" % (time.time() - start_time))
    preds = F.softmax(predict_values, dim=1)
    conf_score, indx = torch.max(preds, dim=1)
    predict_class = classes[indx]
    logger.info(f'Predicted class is {predict_class}')
    logger.info(f'Softmax confidence score is {conf_score.item()}')
    response = {}
    response['class'] = str(predict_class)
    response['confidence'] = conf_score.item()
    return response

def input_fn(request_body):
    """Pre-processes the input data from JSON to PyTorch Tensor.

    Parameters
    ----------
    request_body: dict, required
        The request body submitted by the client. Expect an entry 'url' containing a URL of an image to classify.

    Returns
    ------
    PyTorch Tensor object: Tensor

    """    
    logger.info("Getting input URL to a image Tensor object")
    if isinstance(request_body, str):
        request_body = json.loads(request_body)
    img_request = requests.get(request_body['url'], stream=True)
    img = PIL.Image.open(io.BytesIO(img_request.content))
    img_tensor = preprocess(img)
    img_tensor = img_tensor.unsqueeze(0)
    # return img_tensor



## ================= >> My code starts here


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

