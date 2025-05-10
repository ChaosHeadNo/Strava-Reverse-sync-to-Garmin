import time
import requests
import pandas as pd
import gpxpy.gpx
from datetime import datetime, timedelta
from garminconnect import Garmin
from concurrent.futures import ThreadPoolExecutor
import os


class SqlBody:
    def __init__(self, garmin_user, garmin_password, strava_id, strava_clientsecret, strava_refresh_token, email,
                 password, garmin_location):
        self.garmin_user = garmin_user
        self.garmin_password = garmin_password
        self.strava_id = strava_id
        self.strava_clientsecret = strava_clientsecret
        self.strava_refresh_token = strava_refresh_token
        self.email = email
        self.password = password
        self.garmin_location = garmin_location


class Mynode:
    def __init__(self, tag, attrib, text, tail):
        self.tag = tag
        self.attrib = attrib
        self.text = text
        self.tail = tail
        self._children = []

    def __repr__(self):
        return "<%s %r at %#x>" % (self.__class__.__name__, self.tag, id(self))

    def __len__(self):
        return len(self._children)

    def __getitem__(self, index):
        return self._children[index]

    def __setitem__(self, index, element):
        self._children[index] = element

    def __delitem__(self, index):
        del self._children[index]


class StravaApi:
    def __init__(self, sqlbody):
        self.clientid = sqlbody.strava_id
        self.clientsecret = sqlbody.strava_clientsecret
        self.refresh_token = sqlbody.strava_refresh_token
        self.access_token = None
        self.access_token_expire_time = None
        self.windows_number = 5
        self.active_window = []  # a window to save the previous number of active id

    def _refresh_token(self):
        resoure_list_url = " https://www.strava.com/oauth/token"
        data = {
            'client_id': "client_id", #脚本用户填写""内内容
            'client_secret': "client_secret", #脚本用户填写""内内容
            'refresh_token': "refresh_token", #脚本用户填写""内内容
            'grant_type': "refresh_token",
            'f': 'json'
        }
        response = requests.post(resoure_list_url, data=data, verify=False).json()
        try:
            self.access_token = response.get("access_token")
            self.access_token_time = time.time() + response.get("expires_in")
        except:
            raise Exception(response)

    def get_access_token(self):
        if (not self.access_token) or (not self.access_token_expire_time) or (self.access_token_expire_time and time.time()-10 > self.access_token_expire_time):
            self._refresh_token()

    def access_activity_data(self, sysc_num=10):
        self.get_access_token()
        headers = {'Authorization': 'Bearer {}'.format(self.access_token)}
        my_dataset = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers).json()
        active_window = []
        try:
            for act in my_dataset[:sysc_num]:
                start_time = act.get("start_date")
                active_id = act.get("id")
                active_type = act.get("type").lower()
                active_name= act.get("name")
                active_window.append([start_time, active_id, active_name, active_type])
        except:
            raise Exception(my_dataset)
        return active_window

    def get_new_active(self):
        refreshed_aids = self.access_activity_data(self.windows_number)
        if self.active_window:
            lastactive = self.active_window[0]
            IDX = refreshed_aids.index(lastactive)
            new_active = refreshed_aids[:IDX]
        else:
            new_active = refreshed_aids
        self.active_window = refreshed_aids
        return new_active

    def download_gpx(self):
        aids = self.get_new_active()
        filepaths = []
        # Make API call
        for active in aids:
            start_time = active[0]
            id = active[1]
            active_name = active[2]
            active_type = active[3]
            url = f"https://www.strava.com/api/v3/activities/{id}/streams"
            header = {'Authorization': 'Bearer ' + self.access_token}
            latlong_raw = requests.get(url, headers=header, params={'keys': ['latlng']}).json()
            latlong = []
            distance = []
            for raw_data in latlong_raw:
                if raw_data['type'] == 'latlng':
                    latlong = raw_data['data']
                elif raw_data['type'] == 'distance':
                    distance = raw_data['data']
            time_list_raw = requests.get(url, headers=header, params={'keys': ['time']}).json()
            time_list = time_list_raw[1]['data'] if len(time_list_raw) == 2 else None
            # 无时间序列或者坐标的活动直接跳过
            if not time_list or not latlong:
                continue
            altitude_raw = requests.get(url, headers=header, params={'keys': ['altitude']}).json()
            temp = requests.get(url, headers=header, params={'keys': ['temp']}).json()
            heartrate = requests.get(url, headers=header, params={'keys': ['heartrate']}).json()
            watts = requests.get(url, headers=header, params={'keys': ['watts']}).json()
            cadence = requests.get(url, headers=header, params={'keys': ['cadence']}).json()

            temp = temp[0]['data'] if len(temp) == 2 else None
            heartrate = heartrate[1]['data'] if len(heartrate) == 2 else None
            watts = watts[0]['data'] if len(watts) == 2 else None
            cadence = cadence[0]['data'] if len(cadence) == 2 else None
            altitude = altitude_raw[1]['data'] if len(altitude_raw) == 2 else None

            # Create dataframe to store data 'neatly'
            data = pd.DataFrame([*latlong], columns=['lat', 'long'])
            data['altitude'] = altitude
            start = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
            if time_list:
                data['time'] = [(start + timedelta(seconds=t)) for t in time_list]
            data['temp'] = temp
            data['heartrate'] = heartrate
            data['watts'] = watts
            data['cadence'] = cadence
            gpx = gpxpy.gpx.GPX()
            # Create first track in our GPX:
            gpx_track = gpxpy.gpx.GPXTrack()
            gpx.tracks.append(gpx_track)
            # Create first segment in our GPX track:
            gpx_segment = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)
            # Create points:
            for idx in data.index:
                if altitude:
                    point = gpxpy.gpx.GPXTrackPoint(
                        data.loc[idx, 'lat'],
                        data.loc[idx, 'long'],
                        elevation=data.loc[idx, 'altitude'],
                        time=data.loc[idx, 'time']
                    )
                else:
                    point = gpxpy.gpx.GPXTrackPoint(
                        data.loc[idx, 'lat'],
                        data.loc[idx, 'long'],
                        time=data.loc[idx, 'time']
                    )
                ext = Mynode(tag="gpxtpx:TrackPointExtension", attrib={}, text=None, tail=None)
                if data.loc[idx, 'temp']:
                    cext1 = Mynode(tag="gpxtpx:atemp", attrib={},
                                   text=str(data.loc[idx, 'temp']), tail=None)
                    ext._children.append(cext1)
                if data.loc[idx, 'heartrate']:
                    cext2 = Mynode(tag="gpxtpx:hr", attrib={},
                                   text=str(data.loc[idx, 'heartrate']), tail=None)
                    ext._children.append(cext2)
                if data.loc[idx, 'watts']:
                    cext3 = Mynode(tag="gpxtpx:wat", attrib={},
                                   text=str(data.loc[idx, 'watts']), tail=None)
                    ext._children.append(cext3)
                if data.loc[idx, 'cadence']:
                    cext4 = Mynode(tag="gpxtpx:cad", attrib={},
                                   text=str(data.loc[idx, 'cadence']), tail=None)
                    ext._children.append(cext4)
                point.extensions = [ext]
                gpx_segment.points.append(point)
            xmlformat = gpx.to_xml()
            # we need to replace the creator incase garmin will forbiden out upload
            xmlformat = xmlformat.replace("""<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd" version="1.1" creator="gpx.py -- https://github.com/tkrajina/gpxpy">
""", """<gpx creator="StravaGPX" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd" version="1.1" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3">
""")        # add metedata
            xmlformat = xmlformat.replace("<trk>","""  <metadata>
    <link href="connect.garmin.com">
      <text>Garmin Connect</text>
    </link>
    <time>{starttime}</time>
  </metadata>
  <trk>
    <name>{activename}</name>
    <type>{activetype}</type>""".format(starttime=start_time, activename=active_name, activetype=active_type))
            # Write data to gpx fil
            if not os.path.exists("./%s/" % self.clientid):
                os.mkdir("./%s" % self.clientid)
            if not os.path.exists('./%s/%s.gpx' % (self.clientid, start_time)):
                with open('./%s/%s.gpx' % (self.clientid, start_time), 'w') as f:
                    f.write(xmlformat)
                    filepaths.append('./%s/%s.gpx' % (self.clientid, start_time))
        return filepaths



class SycTask:
    def __init__(self, sqlbody):
        self.sqlbody = sqlbody
        self.garmin_user = sqlbody.garmin_user
        self.garmin_password = sqlbody.garmin_password
        self.garmin_location = sqlbody.garmin_location
        self.strava = StravaApi(self.sqlbody)

    def upload_activity_to_garmin(self):
        InChina = True if self.garmin_location == "China" else False
        garmin = Garmin(self.garmin_user, self.garmin_password, InChina)
        self.strava.get_access_token()
        files = self.strava.download_gpx()
        if files:
            garmin.login()
            for file in files:
                try:
                    garmin.upload_activity(file)
                except Exception as err:
                    print(err)
            garmin.logout()

    def connection_test(self):
        error_info = ""
        eror_code = 0
        # test strava
        try:
            api = StravaApi(self.sqlbody)
            api.get_access_token()
            api.access_activity_data()
        except Exception as error1:
            error_info = "strava connection failed. %s" % str(error1)
            eror_code = 1
        try:
            InChina = True if self.garmin_location == "China" else False
            garmin = Garmin(self.garmin_user, self.garmin_password, InChina)
            garmin.login()
        except:
            error_info = "garmin connection failed"
            eror_code = 1
        return eror_code, error_info



def run_sysc_task_for_one_user(task):
    task.upload_activity_to_garmin()

# 以用户名为key记录需要在本轮执行的任务，老的任务也会进行更新，新的任务会加入字典
round_tasks = {}

def refresh_tasks():
    import pymysql
    # 连接数据库拿到最新数据
    db = pymysql.connect(host='localhost', user='zhai', passwd="Nkg@Lvda!123", port=3306, db="strava2garmin5")
    cursor = db.cursor()
    cursor.execute("select * from TestModel_userdata")
    dbdatas = cursor.fetchall()
    for dbdata in dbdatas:
        # 检查数据可靠性，不可靠的数据拿掉
        garmin_user = dbdata[1]
        garmin_password = dbdata[2]
        strava_id = dbdata[3]
        strava_clientsecret = dbdata[4]
        strava_refresh_token = dbdata[5]
        email = dbdata[7]
        password = dbdata[6]
        garmin_location = dbdata[8]
        if email in round_tasks.keys():
            if "NotSet" in [garmin_user, garmin_password, strava_id, strava_clientsecret, strava_refresh_token]:
                # 移除无效任务
                del round_tasks[email]
                continue
            else:
                # 更新当前任务
                task = round_tasks[email]
                task.garmin_user = garmin_user
                task.garmin_password = garmin_password
                if strava_id != task.strava.strava_id or strava_clientsecret != task.strava.strava_clientsecret or strava_refresh_token != task.strava.strava_refresh_token:
                    # 一旦strava信息有更新，必须刷新access token
                    task.strava.strava_id = strava_id
                    task.strava.strava_clientsecret = strava_clientsecret
                    task.strava.strava_refresh_token = strava_refresh_token
                    task.strava.access_token = None
                    task.access_token_expire_time = None
                task.garmin_location = garmin_location
        else:
            if not "NotSet" in [garmin_user, garmin_password, strava_id, strava_clientsecret, strava_refresh_token]:
                task = SycTask(SqlBody(garmin_user, garmin_password, strava_id, strava_clientsecret, strava_refresh_token, email, password, garmin_location))
                round_tasks[email] = task
    db.close()


if __name__ == "__main__":
    body = SqlBody(strava_id="your strava id", #脚本用户填写""内内容
                   strava_clientsecret="your strava client secret", #脚本用户填写""内内容
                   strava_refresh_token="your strava refresh token", #脚本用户填写""内内容
                   garmin_user="your garmin user", #脚本用户填写""内内容
                   garmin_password="your garmin password", #脚本用户填写""内内容
                   email=None, #脚本用户不需要填写, no need to modify
                   password="",#脚本用户不需要填写, no need to modify 
                   garmin_location="China") #国际服些global，国服写China。  (global/china)
    gar = SycTask(body)
    print(gar.upload_activity_to_garmin())

    # print(refresh_tasks())
    # while True:
    #     taskpool = ThreadPoolExecutor(max_workers=10)
    #     # update task from sql database
    #     refresh_tasks()
    #     # create multiple
    #     for email, task in round_tasks.items():
    #         taskpool.submit(run_sysc_task_for_one_user, task)
    #     taskpool.shutdown()
    #     time.sleep(15 * 60)  # update every or over 15 minutes, strava has it's request limit. by default 100 times per 15 min and 1000 requests per day


