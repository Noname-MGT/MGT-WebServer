from mongoengine import *
import hashlib, random, string, time, math

TEAM_MAX_PLAYERS = 3

def load(url):
    connect(host=url)

def hash_string(input):
    return str(hashlib.sha256(input.encode('utf-8')).hexdigest())

def random_string(size=6, chars=string.ascii_uppercase+string.digits+string.ascii_lowercase):
    return ''.join(random.choice(chars) for _ in range(int(size)))


class Account(Document):
    username = StringField(required=True, max_length=20, min_length=1, unique=True)
    password = StringField(required=True)   #no limitations becase password is stored hashed
    team = ReferenceField("Team")

    def change_team(self, new_team):
        if len(new_team.players) >= TEAM_MAX_PLAYERS: 
            print("Error: Team already full!")
            return False

        old_team = self.team
        self.team = new_team

        old_team.players.remove(self)
        new_team.players.append(self)

        if len(old_team.players) <= 0: old_team.delete()
        

class Team(Document):
    name = StringField(required=True, unique=True, min_length=1, max_length=20)
    players = ListField(ReferenceField(Account), max_length=3)


def team_create(name):
    new_team = Team(name=name, players=[]).save()
    return new_team


class Session(Document):
    owner = ReferenceField(Account)

def session_create(owner:Account):
    if Session.objects(owner=owner): return Session.objects(owner=owner)[0]
    return Session(owner=owner).save()

def session_read(id:str):
    if Session.objects(id=id):
        return Session.objects(id=id)[0].owner
    else:
        return None

def session_terminate(id:str):
    return Session.objects(id=id).delete()

def acc_create(username, password):
    return Account(username=username, password=hash_string(password)).save()

def acc_check_access(username, password):
    if Account.objects(username=username):
        return Account.objects.get(username=username).password == hash_string(password)
    else: 
        return False
