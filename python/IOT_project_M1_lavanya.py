import boto3
from PIL import Image
import select
import v4l2capture
import datetime
time_now = ""
from boto.s3.connection import S3Connection
conn = S3Connection('accesskey','secretkey')
TRAINING_BUCKET = "trainingsetimages"
training_bucket = conn.get_bucket(TRAINING_BUCKET)
IMAGES_BUCKET = "lavanyaimage"
images_bucket = conn.get_bucket(IMAGES_BUCKET)

FACE_DETECTED = False
FACE_RECOGNIZED = False

'''
Code to capture distance data
'''
import time
import VL53L0X

# Create a VL53L0X object
tof = VL53L0X.VL53L0X()

# Start ranging
tof.start_ranging(VL53L0X.VL53L0X_BETTER_ACCURACY_MODE)

distance = 0
timing = tof.get_timing()
if (timing < 20000):
    timing = 20000
print ("WELCOME !!! KEEP HAND NEAR SENSOR TO AUTHENTICATE")


for count in range(1,10000):
    distance = tof.get_distance()
    '''if (distance > 0):
        print ("%d mm, %d cm, %d" % (distance, (distance/10), count))
        '''
    if(distance/10 < 9):
            break
    time.sleep(timing/1000000.00)

tof.stop_ranging()


'''
python code to capture images from camera
'''
def take_picture(file_name):
        # Open the video device.
        video = v4l2capture.Video_device("/dev/video0")

        # Suggest an image size to the device. The device may choose and
        # return another size if it doesn't support the suggested one.
        size_x, size_y = video.set_format(1280, 1024)

        # Create a buffer to store image data in. This must be done before
        # calling 'start' if v4l2capture is compiled with libv4l2. Otherwise
        # raises IOError.
        video.create_buffers(1)

        # Send the buffer to the device. Some devices require this to be done
        # before calling 'start'.
        video.queue_all_buffers()

        # Start the device. This lights the LED if it's a camera that has one.
        video.start()

        # Wait for the device to fill the buffer.
        select.select((video,), (), ())

        # The rest is easy :-)
        image_data = video.read()
        video.close()
        image = Image.fromstring("RGB", (size_x, size_y), image_data)
        
        image.save(file_name)
        print "Saved time_now.jpg (Size: " + str(size_x) + " x " + str(size_y) + ")"


#python code for comapring images 
def compare_faces(bucket, key, bucket_target, key_target, threshold=1, region="us-west-2"):
	rekognition = boto3.client("rekognition", region)
	response = rekognition.compare_faces(
	    SourceImage={
			"S3Object": {
				"Bucket": bucket,
				"Name": key,
			}
		},
		TargetImage={
			"S3Object": {
				"Bucket": bucket_target,
				"Name": key_target,
			}
		},
	    SimilarityThreshold=threshold,
	)
	#print response
	return response['SourceImageFace'], response['FaceMatches']

'''
Write everything to DYNAMO DB
timestamp, file_name, face_detected, face_recognized, face_identity
'''

from boto3 import resource
from boto3.dynamodb.conditions import Key


def add_item(table_name, col_dict):
    """
    Add one item (row) to table. col_dict is a dictionary {col_name: value}.
    """
    dynamodb_resource = resource('dynamodb')
    table = dynamodb_resource.Table(table_name)
    response = table.put_item(Item=col_dict)

    return response



time_now =str(datetime.datetime.now().strftime("%d-%m-%yT%H:%M:%SZ"))
file_name=time_now+".jpg"
take_picture(file_name)

#input images into the bucket
client=boto3.client('rekognition')
s3 = boto3.resource('s3')
data = open(file_name,'rb')
s3.Bucket('lavanyaimage').put_object(Key=file_name, Body=data)

'''detect face in the image '''

rekognition = boto3.client("rekognition", "us-west-2")
response = rekognition.detect_faces(Image={
			"S3Object": {
				"Bucket": IMAGES_BUCKET,
				"Name": file_name}},Attributes=['ALL'])

if len(response["FaceDetails"]) > 0 :
        FACE_DETECTED = True
        print("Face detected, calling compare API")
        # get all objects in training bucket
        for key in training_bucket.list():	
                #listofimages = key.name.encode('utf-8')
            
            source_face,matches = compare_faces(TRAINING_BUCKET, key.name, IMAGES_BUCKET,file_name, 3)
            
            # the main source face
            print "Source Face ({Confidence}%)".format(**source_face)

            # one match for each target face
            for match in matches:
                print "Target Face ({Confidence}%)".format(**match['Face'])
                print "  Similarity : {}%".format(match['Similarity'])
                if match['Similarity'] > 50:
                        print("match found - writing to dynamo")
                        FACE_RECOGNIZED = True
                        add_item("Camera", {"timestamp": time_now, "face_detected": FACE_DETECTED,
                                            "face_recognized":FACE_RECOGNIZED,
                                            "face_identity":key.name, "distance":str(distance)})
                        break
                
else:
        print("Face not detected, writing that to dynamo")
        add_item("Camera", {"timestamp": time_now, "face_detected": True,
                                            "face_recognized":False,
                                            "face_identity":"Unknown person", "distance":str(distance)})


        

                




