import awsgi
from flask import Flask, jsonify, request, send_file
from PIL import Image
import json
import io

# from https://spiegelmock.com/2018/09/06/serverless-python-web-applications-with-aws-lambda-and-flask/

app = Flask(__name__)

@app.route('/', methods=['POST'])
def index():
    print(request.files)
    img = request.files['image'].read()
    img = Image.open(io.BytesIO(img))
    width, height = img.size

    response = jsonify(status=200, message='new test', 
        wid=width, hei=height)

    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type",)
    response.headers.add("Access-Control-Allow-Methods", "OPTIONS,POST,GET")

    return response
    # return send_file(img, mimetype='image/gif')

def lambda_handler(event, context):
    return awsgi.response(app, event, context)

if __name__ == '__main__':
    app.run(debug=True)