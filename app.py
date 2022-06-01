import os, yaml, time, requests
import traceback
from flask import Flask, render_template, redirect, Markup, request, jsonify, escape, session
import json
from datetime import date, timedelta, datetime
from mongoengine.queryset.visitor import Q
from threading import Thread
import DBM
import MCAuth as MCA
import McSkinDownloader as MCSD

# Load settings
SETTINGS = {}
settingsPath = "config.yml"

if os.path.exists(settingsPath):
    with open(settingsPath, "r") as settingsFile: SETTINGS = yaml.safe_load(settingsFile)
    print("Loaded Settings:")
    print(SETTINGS)
else:
    print("could not load settings from \""+settingsPath+"\"...")


# Connect to database
DBM.load(f"{SETTINGS['mongodb']['method']}://{SETTINGS['mongodb']['username']}:{SETTINGS['mongodb']['password']}@{SETTINGS['mongodb']['path']}")

def render_mesage(text, error=False):
    return render_template("customMessage.html", PY_MSG=text, PY_ERROR=error)

def request_user():
    if not "authtoken" in request.cookies: return None
    try:
        return DBM.Session.objects.get(id=request.cookies["authtoken"]).owner
    except DBM.DoesNotExist:
        print("ERROR: Invalid Session ID")
        return None



app = Flask(__name__)

@app.route("/test")
def ep_test():
    MCSD.download(request.args["username"], "./static/skins/")
    return render_template("test.html")

@app.route("/auth", methods=["POST"])
def ep_auth():
    username = request.form["username"]
    password = request.form["password"]
    return render_template("auth.html", PY_AUTHSERVERS=MCA.get_authserver_string(), PY_ACCNAME=username, PY_PW=password)

@app.route("/")
def ep_index():
    return render_template("start.html")

@app.route("/user/team")
def ep_team():
    return render_template("viewTeam.html", ACC=request_user(), ALL_TEAMS=["SCK", "CGG", "DGS", "PGR", "GAY", "NKG"])

@app.route("/user/acc")
def ep_account():
    return render_template("viewAccount.html", ACC=request_user())

@app.route("/login")
def ep_login():
    return render_template("login.html")

@app.route("/register")
def ep_register():
    return render_template("register.html")

@app.errorhandler(404)
def page_not_found(e):
    return render_mesage(f"Zu deiner Anfrage mit dem Pfad \"{request.path}\" konntent wir leider keine Ergebnisse finden!", error=True)

@app.before_request
def catcher():
    #parse json
    if request.path == "/api/":
        try:
            jsonObj = json.loads(request.data)
            def escape_json_values(obj):
                if isinstance(obj, dict):
                    cres = {}
                    for k, v in obj.items():
                        cres[k] = escape_json_values(v)
                    return cres
                elif isinstance(obj, list):
                    cres = []
                    for cv in obj:
                        cres.append(escape_json_values(cv))
                    return cres
                else:
                    return str(escape(obj))
            jsonObj = escape_json_values(jsonObj)
            request.data = json.dumps(jsonObj)
        except json.JSONDecodeError:
            print(f"Error parsing json \"{request.data.decode()}\"")
            return "Error processing Json...", 400
    
    if request.path.startswith("/user/") and not "authtoken" in request.cookies:
        return redirect("/login")
            

@app.route("/api/", methods=["POST"])
def ep_api():
    global orders, opened, baught
    rqd:json = json.loads(request.data)
    ok = False
    response = {}
    try:
        cmd:str = rqd["cmd"]
        args:dict = rqd["args"]
        
        if cmd == "session_terminate":
            DBM.session_terminate(request.cookies["authtoken"])
            ok = True

        if cmd == "user_login":
            if DBM.acc_check_access(args["username"], args["password"]):
                response ["authsync"] = str(DBM.session_create(DBM.Account.objects(username=args["username"])[0]).id)
                response ["usernamesync"] = str(args["username"])
                ok = True

        if cmd == "user_register":
            if not DBM.Account.objects(username=args["username"]):
                token = args["authtoken"]
                if MCA.token_by_name(args["username"]) == token:
                    MCA.remove_token_for(args["username"])
                    DBM.acc_create(args["username"], args["password"])
                    MCSD.download(args["username"], "./static/skins/")
                    response["msg"] = "Erfolgreich registriert"
                    ok = True
                else:
                    response["msg"] = "Falscher Token"
            else:
                response["msg"] = "Dieser Account wurde schon registriert"
        
        if cmd == "user_preregister":
            if requests.get("https://api.mojang.com/users/profiles/minecraft/"+str(args["username"])).status_code == 200:
                if not DBM.Account.objects(username=args["username"]):
                    MCA.create_token_for(args["username"])
                    ok = True
                else:
                    response["msg"] = "Dieser Account wurde schon registriert"
            else:
                response["msg"] = "Es gibt keinen MinecraftAccount mit diesem Namen"

        if cmd == "ping":
            response["msg"] = "pong"
            response["mirror"] = args["mirror"]
            ok = True

        if request_user() is not None:
            if cmd == "accdelete":
                if request_user() is not None:
                    request_user().delete()
                    DBM.session_terminate(request.cookies["authtoken"])
                    ok = True

            if cmd == "team_create":
                nteam = DBM.team_create(args["teamname"])
                request_user().change_team(nteam)
                ok = True
            
            if cmd == "team_switch":
                nteam = DBM.Team.objects(name=args["teamname"]).get()
                print("NT: "+str(nteam))
                request_user().change_team(nteam)
                ok = True

        if cmd == "MCAUTHENTICATION":
            if args["authenticationToken"] == SETTINGS["mcauth"]["accesstoken"]:
                method = args["method"]

                if method == "register": MCA.provider_register(args["address"])
                if method == "deregister": MCA.provider_deregister(args["address"])

                if method == "get_token": response["token"] = MCA.token_by_name(args["playername"])
                
                ok = True
                print("Providers: "+str(MCA.providers))

    except KeyError as e:
        ok = False
        return "missing argument ("+str(e)+")", 400
    except Exception:
        ok = False
        response["fatal"] = "You screwed up!"
        print(traceback.format_exc())
    

    response["ok"] = ok
    print(f"API-FETCH[{request_user().username if request_user() != None else ''}] {rqd} --> {response}")
    return jsonify(response)


#make sure all users skins are downloaded
print("Downloading all users skins...")
for ca in DBM.Account.objects:
    try:
        if not os.path.exists("./static/skins/"+ca.username+".png"):
            print("Dowloading "+ca.username+"'s skin...")
            MCSD.download(ca.username, "./static/skins/")
    except json.decoder.JSONDecodeError:
        print("Could not download "+ca.username+"'s skin...")

#start flask debug server
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=31313, debug=True, threaded=True)