# this import statement is needed if you want to use the AWS Lambda Layer called "pytorch-v1-py36"
# it unzips all of the pytorch & dependency packages when the script is loaded to avoid the 250 MB unpacked limit in AWS Lambda
try:
    import unzip_requirements
except ImportError:
    pass

# import os
import io
import json
# import logging
import base64
import boto3
import torch

# our library
from RetinaNetAndAuxillaries import *

# need requirements.txt file for this to work!
from fastai.vision import *


# load the S3 client when lambda execution context is created
s3 = boto3.client('s3')

# classes for the image classification

# logger = logging.getLogger()
# logger.setLevel(logging.INFO)

# get bucket name from ENV variable
# MODEL_BUCKET = os.environ.get('MODEL_BUCKET')
# logger.info(f'Model Bucket is {MODEL_BUCKET}')

# get bucket prefix from ENV variable
# MODEL_KEY = os.environ.get('MODEL_KEY')
# logger.info(f'Model Prefix is {MODEL_KEY}')


def load_model():
    """Loads the PyTorch model into memory from a file on S3.

    Returns
    ------
    Vision model: learn
        Returns the vision fastai model to use for inference.

    """      
    logger.info('Loading model from S3')

    m_key = 'models/stage2-256-exp.pkl'
    bucket = 'objdetection-orozcobusch'
    obj = s3.get_object(Bucket=bucket, Key=m_key)
    # bytestream = io.BytesIO(obj['Body'].read())

    learn = load_learner(path='.', file=io.BytesIO(obj['Body'].read()))

    return learn


# =======>> uncomment fo production

# load the model when lambda execution context is created
learn = load_model()


def process_output2(output, i, detect_thresh=0.25):
    """AB: ratios and scales are added, hardcoded"""
    ratios = [1 / 2, 1, 2]
    scales = [1,2**(-1 / 3), 2**(-2 / 3)]
    clas_pred,bbox_pred,sizes = output[0][i], output[1][i], output[2]
    anchors = create_anchors(sizes, ratios, scales).to(clas_pred.device)
    bbox_pred = activ_to_bbox(bbox_pred, anchors)
    clas_pred = torch.sigmoid(clas_pred)
    detect_mask = clas_pred.max(1)[0] > detect_thresh
    bbox_pred, clas_pred = bbox_pred[detect_mask], clas_pred[detect_mask]
    bbox_pred = tlbr2cthw(torch.clamp(cthw2tlbr(bbox_pred), min=-1, max=1))    
    if clas_pred.numel() == 0: return [],[],[]
    scores, preds = clas_pred.max(1)
    return bbox_pred, scores, preds


def show_preds2(img, output, idx, detect_thresh=0.25, classes=None, ax=None):
    """AB: ratios and scales are added in process_output2, hardcoded"""

    bbox_pred, scores, preds = process_output2(output, idx, detect_thresh)
    if len(scores) != 0:
        to_keep = nms(bbox_pred, scores)
        bbox_pred, preds, scores = bbox_pred[to_keep].cpu(), preds[to_keep].cpu(), scores[to_keep].cpu()
        t_sz = torch.Tensor([*img.size])[None].float()
        bbox_pred[:,:2] = bbox_pred[:,:2] - bbox_pred[:,2:] / 2
        bbox_pred[:,:2] = (bbox_pred[:,:2] + 1) * t_sz / 2
        bbox_pred[:,2:] = bbox_pred[:,2:] * t_sz
        bbox_pred = bbox_pred.long()
    if ax is None: fig, ax = plt.subplots(1,1)
    img.show(ax=ax)
    for bbox, c, scr in zip(bbox_pred, preds, scores):
        txt = str(c.item()) if classes is None else classes[c.item() + 1]
        draw_rect(ax, [bbox[1],bbox[0],bbox[3],bbox[2]], 
            text=f'{txt} {scr:.2f}')
    # AB: added to have the output as a file

    # save image in memory
    buff = io.BytesIO()
    fig.savefig(buff)

    return buff


def get_classes():
    '''get the classes for the predictions'''

    return ['background', 'aeroplane', 'bicycle', 'bird', 'boat',
    'bottle', 'bus', 'car', 'cat', 'chair', 'cow', 'diningtable',
    'dog', 'horse', 'motorbike', 'person', 'pottedplant', 'sheep',
    'sofa', 'train', 'tvmonitor']


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

    # fastai method
    img = open_image(io.BytesIO(decoded))

    return img


def analyze(img):
    '''Run main algorithm'''

    # cuda for using CPU, unsqueeze for simulating a bunch of images,
    # resize for equivalent image, acutally not necessary
    # learn.predict(img.resize(256).data.unsqueeze(0)) is errorneous
    # thats why torch.no_grad is used

    with torch.no_grad():
        output = learn.model(img.resize(256).data.unsqueeze(0))

    classes_list = get_classes()

    img = show_preds2(img, output, 0, detect_thresh=0.25, 
        classes=classes_list, ax=None)

    return img


def get_output(buff):
    '''input a buffer of loaded image, return an encoded base64 string
    ready for html parsing'''

    # from: https://stackoverflow.com/questions/48229318/
    # how-to-convert-image-pil-into-base64-without-saving?rq=1

    header = 'data:image/png;base64,'

    return header + base64.b64encode(buff.getvalue()).decode('UTF-8')


def lambda_handler(event, context):
    '''AWS Lambda handler. A base64 encoded image is expected in 
    event["body"]. Returns an annotated image'''

    img = get_input(event)

    img_buffer = analyze(img)

    enc_img = get_output(img_buffer)


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

