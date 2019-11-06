#! /usr/bin/python3

#RESTful API services for crumpitManager
#
#Author: Jez Swann
#Date: May 2019
#Tutorial: http://blog.luisrei.com/articles/flaskrest.html
#Mongo JSON conversion adapted from https://gist.github.com/akhenakh/2954605

import base64
import pathlib

import logging
from flask import Flask, url_for, request
try:
    import simplejson as json
except ImportError:
    try:
        import json
    except ImportError:
        raise ImportError
import datetime
from bson.objectid import ObjectId
from werkzeug import Response

import app.config
from app.liveRuns.runsInfo import *
from app.clusterInfo import *
from app.metadata.metaDataConnection import *

class MongoJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        elif isinstance(obj, ObjectId):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

def jsonify(*args, **kwargs):
    """ jsonify with support for MongoDB ObjectId
    """
    return Response(json.dumps(dict(*args, **kwargs), cls=MongoJsonEncoder), mimetype='application/json')

def setup_logging():
    logger = logging.getLogger("api")
    logger.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    f_handler = logging.FileHandler("api.log")
    c_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    f_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(f_handler)
    logger.addHandler(c_handler)

def reload_cfg():
    global configFile
    global cfg
    configFile = pathlib.Path("configs/config.yaml")

    cfg = app.config.Config()
    cfg.load(str(configFile))

def getRunsInfo():
    try:
        mongoDBcfg = cfg.get('mongoDB')
    except Exception as e:
        return runsInfo()       
    try:
        mongoDBcfg['port']
    except Exception as e:    
        return runsInfo(mongoDBcfg['ip'])
    
    return runsInfo(mongoDBcfg['ip'], mongoDBcfg['port'])

def getMetadata():
    try:
        sqlDBcfg = cfg.get('sqlDB')
    except Exception as e:
        return metaDataConnection()
    try:
        sqlDBcfg['port']
    except Exception as e:    
        return metaDataConnection(sqlDBcfg['ip'])
    
    return metaDataConnection(sqlDBcfg['ip'], sqlDBcfg['port'])

setup_logging()
logger = logging.getLogger('api')
logger.debug("Logging initialized")
reload_cfg()

app = Flask(__name__)

@app.route('/',methods = ['GET'])
def api_root():
    rs = [1,'Welcome to crumpit Manager APIs']	
    return generateResponse(rs,200) 

@app.route('/liveRuns',methods = ['GET'])
def getRuns():
    try:
        rs = [1, getRunsInfo().getRuns()]
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "could not connect to mongo db"]

    return generateResponse(rs,200) 

@app.route('/liveRuns/graph',methods = ['GET'])
def getRunsGraph():
    runsInfo = None
    try:
        runsInfo = getRunsInfo()
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "could not connect to mongo db"]
        return generateResponse(rs, 200)

    try:
        filename = runsInfo.getRunsGraph()
        if isinstance(filename, str):
            runGraph = open(filename, 'rb')
            image_read = runGraph.read()
            image_64_encode = base64.encodestring(image_read)
            image_64_string = image_64_encode.decode('utf-8')
            imageDict = {
                "image" : image_64_string
            }
            rs = [1, imageDict]
            return generateResponse(rs, 200)
        else:
            rs = [0, "Could not create Image"]
            return generateResponse(rs, 500)
    except Exception as e:
        logger.debug(str(e))
        rs = [0, "Could not create Image"]
        return generateResponse(rs, 500)

@app.route('/liveRuns/liveStats',methods = ['GET'])
def getLiveStats():
    try:
        rs = [1, getRunsInfo().getLiveStats()]
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "Error Getting liveStats"]

    return generateResponse(rs,200)

@app.route('/metadata/runs',methods = ['GET'])
def getMetadataRuns():
    try:
        rs = [1, getMetadata().getPreRunInfo()]
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "could not connect to SQL db"]

    return generateResponse(rs,200) 

@app.route('/metadata/run',methods = ['GET'])
def getMetadataRun():
    try:
        rs = [1, getMetadata().getPreRunFields()]
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "could not connect to SQL db"]

    return generateResponse(rs,200) 

@app.route('/metadata/run/defaultBarKit/<seqKit>',methods = ['GET'])
def getdefaultBarKit(seqKit):
    try:
        preRunFields = getMetadata().getPreRunFields()
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "could not connect to SQL db"]

    try:
        barKit = preRunFields['sequenceKits'][seqKit]
        rs = [1, barKit]
    except Exception as e:
        logger.debug(str(e))
        rs = [-1, "Sequencing Kit not valid"]


    return generateResponse(rs,200) 

@app.route('/metadata/run',methods = ['POST'])
def addRun():
    if 'json' in request.headers['Content-Type']:
        try:
            data = request.json
            try:
                print("Params:" + str(data.items()))
            except:
                return generateResponse([0 ,"Invalid parameter"])

            rs = [1, getMetadata().addRun(data)]
        except Exception as e:
            logger.debug(str(e))
            rs = [-1, "could not connect to SQL db"]

    else:
        return generateResponse([0,"Unsupported Media Type"])

    return generateResponse(rs,200) 

@app.route('/backups',methods = ['GET'])
def getRunBackups():
    dbRuns = getRunsInfo().getRuns()
    rs = [1, clusterInfo().getBackupInfo(cfg.get('logDir'), dbRuns, cfg.get('clusterInfo')['remoteStorage'])]
    return generateResponse(rs,200) 

@app.route('/clusterInfo',methods = ['GET'])
def getClusterInfo():
    localInfo = clusterInfo().getLocalInfo(cfg.get('clusterInfo'))
    remoteInfo = clusterInfo().getRemoteInfo(cfg.get('clusterInfo')['remoteStorage'])
    combinedInfo = {'localInfo': localInfo, 'remoteInfo': remoteInfo}
    rs = [1, combinedInfo]
    return generateResponse(rs,200)

#input: result is an array
#result[0] = 0 for OK -- else for error 
#result[1] = data or error message
#Status code list = http://www.flaskapi.org/api-guide/status-codes/
def generateResponse(result, statusCode = None):
    if statusCode is None:
        if result[0] == 0:
            statusCode = 200
        else:
            statusCode = 500

    rs = {}
    rs["status"] = result[0]	
    rs["data"] = result[1]
    resp = jsonify(rs)
    resp.status_code = statusCode		
    return resp

if __name__ == '__main__':
    port = 5607
    try:
        port = cfg.get('flask')['port']
        logger.debug("Using flask port %d", port)
    except Exception as e: 
        logger.debug("Using default flask port 5607")
        
    app.run(host='0.0.0.0', port=port)
