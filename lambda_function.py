import cv2
import urllib
import numpy as np
import logging
import os
import subprocess
import json
import boto3

log = logging.getLogger()
log.setLevel(logging.DEBUG)

DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(DIR, 'tesseract-lambda')
LIB_DIR = os.path.join(SCRIPT_DIR, 'lib')
BUCKET = 'slackbot-bucket'

response_template = {
    "username": "CMD. Parser",
    "icon_emoji": ":cop::skin-tone-2:",
    "text": "",
    "attachments": [
        {
            "text": "Here is what you sent",
            "image_url": ""
        }
        ]
    }


def get_url(event):
    trigger_word = event['trigger_word']
    raw_text = event['text']
    url = raw_text.replace(trigger_word, '').strip()
    resp = urllib.urlopen(url)
    if 'image' in resp.headers['Content-Type']:
        return url, resp
    else:
        return url, False


def read_alter_write_image(contents, image_path):
    image = np.asarray(bytearray(contents), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_GRAYSCALE)
    log.debug(image)
    img = cv2.resize(image, (0,0), fx=3, fy=3)
    ret,th1 = cv2.threshold(img,127,255,cv2.THRESH_BINARY)
    # th2 = cv2.adaptiveThreshold(img,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,11,2)
    # th3 = cv2.adaptiveThreshold(img,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,11,2)
    cv2.imwrite(image_path, th1)


def do_tessseract(image_path, text_path):
    command = 'LD_LIBRARY_PATH={} TESSDATA_PREFIX={} {}/tesseract {} {}'.format(
        LIB_DIR,
        SCRIPT_DIR,
        SCRIPT_DIR,
        image_path,
        text_path,
    )
    log.debug(command)
    output = subprocess.check_output(command, shell=True)


def parse_ocr_output(text_path):
    with open(text_path, 'rb') as f:
        ocr = f.read()
    num_of_commands = ocr.count('$')
    i = 0
    end = 0
    commands = ''
    while i < num_of_commands:
        start = ocr.find('$', end)
        end = ocr.find('\n', start)
        i += 1
        commands = commands + ocr[(start+1):end] + '\n'
    return commands


def create_response(commands, url):
    response = response_template
    response['text'] = commands
    response['attachments'][0]['image_url']= url
    return response



def lambda_handler(event, context):
    url, resp = get_url(event)
    if resp:
        s3_client = boto3.client('s3')
        stripped_time = event['timestamp'][:event['timestamp'].find('.')]
        uuid = event['team_domain'] + '_' + stripped_time
        image_path = '/tmp/' + uuid + '.jpg'
        text_path = '/tmp/' + uuid

        read_alter_write_image(resp.read(), image_path)
        s3_client.upload_file(image_path, BUCKET, uuid + '.jpg')
        do_tessseract(image_path, text_path)
        s3_client.upload_file(text_path + '.txt', BUCKET, uuid + '.txt')
        commands = parse_ocr_output(text_path + '.txt')
        response = create_response(commands, url)
        return response
    else:
        response = response_template
        response['text'] = "Sir, that is not a valid image URL. Get down, gimme 20 and send a valid URL"
        return response
