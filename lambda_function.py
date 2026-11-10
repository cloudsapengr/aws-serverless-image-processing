
import json
import os
import boto3
import urllib.parse
import uuid

from datetime import datetime, timezone
from io import BytesIO
from PIL import Image

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

DESTINATION_BUCKET = "aws-serverless-image-processed-101126"
TABLE_NAME = "ImageProcessingMetadata"
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):

    for record in event["Records"]:

        source_bucket = record["s3"]["bucket"]["name"]
        object_key = urllib.parse.unquote_plus(
            record["s3"]["object"]["key"]
        )

        print("Source bucket:", source_bucket)
        print("Original image:", object_key)

        if not object_key.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):
            print("Unsupported image:", object_key)
            continue

        image_id = str(uuid.uuid4())
        original_name = object_key.split("/")[-1]

        response = s3.get_object(
            Bucket=source_bucket,
            Key=object_key
        )

        image_data = response["Body"].read()

        image = Image.open(BytesIO(image_data))
        image.thumbnail((300, 300))

        output = BytesIO()
        image = image.convert("RGB")
        image.save(output, format="JPEG", quality=85)
        output.seek(0)

        thumbnail_key = f"thumbnails/{image_id}.jpg"

        upload_result = s3.put_object(
            Bucket=DESTINATION_BUCKET,
            Key=thumbnail_key,
            Body=output.getvalue(),
            ContentType="image/jpeg"
        )

        print("S3 upload response:", upload_result)

        verification = s3.head_object(
            Bucket=DESTINATION_BUCKET,
            Key=thumbnail_key
        )

        print("S3 upload verified successfully")
        print("Verified bucket:", DESTINATION_BUCKET)
        print("Verified key:", thumbnail_key)
        print("Verified file size:", verification["ContentLength"])

        table.put_item(
            Item={
                "image_id": image_id,
                "original_bucket": source_bucket,
                "original_filename": original_name,
                "thumbnail_bucket": DESTINATION_BUCKET,
                "thumbnail_key": thumbnail_key,
                "status": "COMPLETED",
                "processed_at": datetime.now(
                    timezone.utc
                ).isoformat()
            }
        )

        print("DynamoDB metadata saved successfully")

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="Image processing completed",
            Message=json.dumps({
                "image_id": image_id,
                "original_filename": original_name,
                "thumbnail_bucket": DESTINATION_BUCKET,
                "thumbnail_key": thumbnail_key,
                "status": "COMPLETED"
            })
        )

        print("SNS notification sent successfully")
        print("Successfully processed:", original_name)

    return {
        "statusCode": 200,
        "body": "Image processing completed"
    }
