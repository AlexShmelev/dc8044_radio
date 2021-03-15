#!/usr/bin/env python3

# Yea i know this script can be better, but i'm a lazy person (c) shmel'

import sys
import json
import random
import requests
import datetime
from copy import deepcopy as dcp
from time import sleep
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta

day_min         = 1440
username        = '<PUT_YOUR_LOGIN_HERE>'
password        = '<AND_PASSWORD_HERE>'
playlist_url    = 'https://studio.radio.co/api/v1/stations/s883dfeaeb/playlists'
schedule_url    = 'https://studio.radio.co/api/v1/stations/s883dfeaeb/schedule'
# rules           = [1,1,1,1,1,1,1,2,2,2,2,2,2,2,2,2,2]
# rules           = [4,3,2,1,1,1,2,2,2,3,3,4,3,2,3,3,3,4,4,4,4,4,4]

@dataclass
class Playlist:
    id: int
    length: int

class bc:
    ENDC  = '\033[0m'
    OK    = f'[\033[92m OK {ENDC}] '
    WARN  = f'[\033[93mWARN{ENDC}] '
    FAIL  = f'[\033[91mFAIL{ENDC}] '
    INFO  = f'[    ] '

def msg(msg, status=bc.OK):
  print(status + msg)

def panic(msg):
  print(f'---------- {msg} ----------')
  sys.exit(1)

def debug(msg):
  print(f'### {msg} ###')

def hm2m(time):
  if 'h' in time:
    hours = int(time.split('h')[0])
    if 'm' in time:
      minutes = int(time.split('h')[1].split('m')[0])
    else:
      minutes = 0
    minutes = hours * 60 + minutes
  else:
    minutes = int(time.split('m')[0])
  return minutes

# Login to radio, return authed session, nothing interesting
def radio_login(username, password):
  msg('Tryin to get authenticated session...',bc.INFO)
  login = 'https://studio.radio.co/login_check'
  session = requests.Session()
  l = session.get(login)
  soup = BeautifulSoup(l.content,'lxml')
  values = {'_username': username,
            '_password': password,
            '_submit' : 'Sign+in',
            '_remember_me' : 'on',
            '_csrf_token' : soup.find('input')['value']}
  post_resp = session.post(login, data = values)
  if post_resp.status_code != 200:
    msg(f'Expeceted response 200, got {post_resp.status_code}! Exiting', bc.FAIL)
    sys.exit()
  else:
    msg('Looks like we got session!')
  return session

# Request playlist json, and parse it into small dict [id, name]
def request_playlists(session):
  msg('Tryin to request playlists...',bc.INFO)
  # Get playlist json response
  pl_resp             = session.get(playlist_url)
  if pl_resp.status_code != 200:
    msg(f'Expeceted response 200, got {pl_resp.status_code}! Exiting', bc.FAIL)
    sys.exit()
  else:
    msg('Playlists obtained! Parsing...')
  all_pl_json         = pl_resp.json()
  # Generate dict [id, name]
  id_names_dict       = [[playlist['id'], playlist['name']] for playlist in all_pl_json['playlists']]
  # Generate dict [id, [date, user, mood, name, time]] ; exclude all incorrectly formated names
  id_namesParsed_dict = [[row[0], row[1].split('/')] for row in id_names_dict if len(row[1].split('/')) == 5]

  for i in range(len(id_namesParsed_dict)):
    id_namesParsed_dict[i][1][4] = hm2m(id_namesParsed_dict[i][1][4])

  return id_namesParsed_dict

def get_pl_struct(parsed_playlist):
  playlists = {'prime': {'1': [], '2': [], '3': [], '4': []}, 'noprime': {'X': [], 'N': []}}
  for pl in parsed_playlist:
    pl_mood = str(pl[1][2])
    pl_id   = int(pl[0])
    pl_time = int(pl[1][4])
    if (pl_mood == 'X') or (pl_mood == 'N'):
      playlists['noprime'][pl_mood].append(Playlist(pl_id,pl_time))
    else:
      playlists['prime'][pl_mood].append(Playlist(pl_id,pl_time))

  return playlists

# TODO: debug overrun
def generate_json_post(playlist_id,timeStart,timeEnd):
  msg('Generating json payload', bc.INFO)
  json_str = ({'start': timeStart,
              'end': timeEnd,
              'repeat': False,
              'overrun': False,
              'record': False,
              'metadata':'adaptive',
              'days':[{'day':'Monday','num':2,'display':'Mon'},
                      {'day':'Tuesday','num':4,'display':'Tues'},
                      {'day':'Wednesday','num':8,'display':'Weds'},
                      {'day':'Thursday','num':16,'display':'Thurs'},
                      {'day':'Friday','num':32,'display':'Fri'},
                      {'day':'Saturday','num':64,'display':'Sat'},
                      {'day':'Sunday','num':1,'display':'Sun'}],
              'playlist_id': int(playlist_id),
              'relay_id': None,
              'collaborator_id': None})
  return json_str

def post_sched_event(session, data):
  msg('Posting schedule event...', bc.INFO)
  post_resp = session.post(schedule_url,data=data)
  if post_resp.status_code != 201:
    debug(f'post_resp   : {post_resp.status_code}')
    # If json error code == 409, then we get event collision (current timeslot taken)
    if post_resp.json()['errors'][0]['code'] == 409:
      event_id = post_resp.json()['collisions']['event_id']
      msg('Found collision: ' + str(event_id) + ' trying to remove', bc.WARN)
      # tryin to delete collision event
      delete_sched_event(session,event_id)
      post_sched_event(session,data)
  else: msg('Post succcesful')

def delete_sched_event(session, event):
  msg('Delete scheduled event', bc.INFO)
  delete_repsonse = session.delete(str(schedule_url) + '/' + str(event))
  if delete_repsonse.status_code != 204:
    msg(f'Something went wrong. Can\'t delete event{event_id}', bc.FAIL)
    sys.exit()
  else: msg('Delete succcesful')

# Return time as 2021-01-28T09:30:00.000Z
def convert_min_to_time(weeknum,weekday,min):
  d = f"{datetime.utcnow().year}-W{weeknum}"
  target_date = datetime.strptime(d + '-1', "%Y-W%W-%w") # get monday by weeknum for curr year
  target_date = target_date + timedelta(minutes=min) + timedelta(days=weekday)  # add delta minutes
  target_date = target_date + timedelta(hours=-2)                               # -2 hours
  formated_time  = target_date.strftime('%Y-%m-%dT%H:%M:00.000Z')
  return formated_time

def roll_for_pl(day_playlists,mood,playlists):
  prime_mode = 'noprime' if (mood == 'N') or (mood == 'X') else 'prime'
  while True:
    pl = random.choice(playlists[prime_mode][mood])
    # Round prime pl - 2 hours
    if prime_mode == 'prime':
      if pl.length >= 120:
        pl.length = 120
    # Check if playlist already used
    if day_playlists.count(pl) == 0:
      break
  return pl

def sched_degub(day_playlists):
  total_time  = sum([int(pl.length) for pl in day_playlists])
  total_count = len(day_playlists)
  all_lenghts = [pl.length for pl in day_playlists]
  print(f"all_lenghts:      {all_lenghts}")
  print(f"total_count:      {total_count} playlists")
  print(f"total_time:       {total_time}  minutes")

def get_pl_by_id(id):
  result = [ pl for pl in id_namesParsed_list if pl[0] == id ]
  return result

def make_sched(week):
  week_post = []
  for day in week:
    timer     = 0
    day_post  = []
    for pl in day:
      full_pl     = get_pl_by_id(pl.id) # Get only info without id
      PL_name     = full_pl[0][1][3]
      start_time  = '{:02d}:{:02d}'.format(*divmod(timer, 60))
      timer      += pl.length
      post        = f"{start_time} - {PL_name}"
      day_post.append(post)
    week_post.append(day_post)
  return week_post

def put_week_sched(session,weeknum,week_playlist):
  weekday = 0
  for day_playlists in week_playlist:
    counter = 0
    for pl in day_playlists:
      TS = convert_min_to_time(weeknum,weekday,counter)
      counter += pl.length
      TN = convert_min_to_time(weeknum,weekday,counter)
      preparedJson = generate_json_post(str(pl.id),TS,TN)
      post_sched_event(session,preparedJson)
    weekday += 1


####################################################################################################
####################################################################################################
####################################################################################################


def run(weeknum):
  week_plan = [
  [['N',60],  ['X',120], ['1',180], ['2',120], ['3',120], ['4',60],  ['3',60],  ['2',60],  ['3',180], ['4',420], ['N',60]],
  [['N',120], ['2',120], ['1',180], ['2',120], ['3',60],  ['4',60],  ['3',60],  ['2',60],  ['3',180], ['4',300], ['3',60],  ['N',120]],
  [['N',60],  ['X',180], ['1',180], ['2',60],  ['3',240], ['4',60],  ['3',120], ['2',60],  ['3',180], ['4',60],  ['3',120], ['N',120]],
  [['N',240], ['1',180], ['2',180], ['3',300], ['2',120], ['3',180], ['2',120], ['N',120]],
  [['N',120], ['X',120], ['1',120], ['2',120], ['3',240], ['4',240], ['3',180], ['4',240], ['3',60]],
  [['3',180], ['X',180], ['2',120], ['1',240], ['2',180], ['3',240], ['2',120], ['X',120], ['N',60]],
  [['X',60],  ['N',120], ['1',180], ['X',120], ['3',240], ['2',120], ['3',180], ['N',60],  ['3',60], ['2',120], ['1',60], ['N',120]],
  ]
  global day_min, username, password, playlist_url, schedule_url, rules, id_namesParsed_list
  session = radio_login(username, password)
  id_namesParsed_list = request_playlists(session)
  playlists = get_pl_struct(id_namesParsed_list)

  week_playlist = []
  for day_plan in week_plan:
    day_playlists = []
    for mood, mood_length_minutes in day_plan:
      minutes_fill_left = mood_length_minutes
      while True:
        pl = dcp(roll_for_pl(day_playlists,mood,playlists))
        diff = (minutes_fill_left - pl.length)
        if diff != 0:
          if diff < 30 and diff > 0:
            continue # Try again
        if pl.length >= minutes_fill_left:
          pl.length = minutes_fill_left
          day_playlists.append(pl)
          break
        day_playlists.append(pl)
        minutes_fill_left -= pl.length
    week_playlist.append(day_playlists)

  put_week_sched(session,weeknum,week_playlist)
  for day in make_sched(week_playlist):
    print('##########################')
    for event in day:
      print(event)

if len(sys.argv) < 2:
  print(f"Usage: {sys.argv[0]} <weeknumber>")
  sys.exit(1)

run(sys.argv[1])
