from flask import Flask,request,jsonify
import boto3 
import requests
from PIL import Image
import uuid
import os
import time

import psycopg2
conn = psycopg2.connect(database = 'DATABASE',user = 'postgres',password = '',host = 'Localhost',port = '5432')
cursor = conn.cursor()

def remove_bg(image_path):
    filename = str(uuid.uuid4()) + '.png'
    print(filename)
    response = requests.post(
        'https://api.remove.bg/v1.0/removebg',
        files={
            'image_file': open(image_path, 'rb')
        },
        data={
            'size': 'auto'
        },
        headers={
            'X-Api-Key': ''
        },
    )
    if response.status_code == requests.codes.ok:
        with open(f'{filename}', 'wb') as out:
            out.write(response.content)
    else:
        print("Error:", response.status_code, response.text)

    img = Image.open(f'{filename}')
    img = img.resize((700, 700), Image.Resampling.LANCZOS)
    img.save(f'{filename}')

    s3 = boto3.client(
        's3', 
        aws_access_key_id='', 
        aws_secret_access_key=''
    )

    with open(f'{filename}', 'rb') as file:
        s3.put_object(Body=file, Bucket='bgremoved-images-new', Key=f'{filename}')

    image_url = f"{s3.meta.endpoint_url}/bgremoved-images-new/{filename}"

    return [filename, image_url]

def name_from_textract(image_id):
    textract = boto3.client(
        'textract', 
        aws_access_key_id='',
        aws_secret_access_key = '',
        region_name=''
    )
    response = textract.detect_document_text(
        Document={
            'S3Object': {
                'Bucket': 'bgremoved-images-new',
                'Name': image_id
            }
        }
    )

    max_area = 0
    largest_text = ''
    specific_height = 0.03 
    for item in response["Blocks"]:
        if item["BlockType"] == "LINE":
            width = item['Geometry']['BoundingBox']['Width']
            height = item['Geometry']['BoundingBox']['Height']
            area = width * height
            if area > max_area and height > specific_height:
                max_area = area
                largest_text = item["Text"]
    return largest_text

def elastic_search(search_query):
    url = ''
    headers = {
        'Content-Type': 'application/json',
        'Authorization': ''
    }
    data = {
        "query": search_query,
        "page": {
            "current": 1,
            "size": 100
        },
        "filters": {
            "approved": ["0"]
        }
    }

    response = requests.get(url, headers=headers, json=data)

    return response.json()


def process_image(image_path):
    res = remove_bg(image_path)
    search_query = name_from_textract(res[0])
    search_res = elastic_search(search_query)
    data = {
        'Elastic_search_output':search_res,
        'Image_url':res[1],
        'Search_query':search_query
        
    }
    cursor.execute(
    '''
        INSERT INTO image_search_responses (image_link, text, elastic_search_response)
        VALUES (%s, %s, %s)
    ''',(res[1], search_query, str(search_res))
    )
    conn.commit()

if __name__ == '__main__':
    image_folder = "D:/EVITAL_PROD_IMAGES/Medicine_images/"
    image_files = os.listdir(image_folder)
    for image in image_files:
        image_path = os.path.join(image_folder, image)
        process_image(image_path)