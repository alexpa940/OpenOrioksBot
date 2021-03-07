# -*- coding: utf-8 -*-

import vk_api
import telebot
import re
import os, sys
import threading
import _pickle
import json
import time
import copy
import datetime
import dateutil.parser
import configparser
import traceback
import collections
import requests
import random



from bs4 import BeautifulSoup
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from telebot import apihelper
from vk_api.utils import get_random_id

LOCK = threading.Lock()
USERDATA = {} # данные юзеров
BOTS = {}
LOCAL_PATH = os.path.abspath(os.path.dirname(sys.argv[0])) # путь к этому файлу (main.py)
DATA_PATH = os.path.join(LOCAL_PATH, 'userdata.dat') # путь к файлу с данными юзеров
VKACC_PATH = os.path.join(LOCAL_PATH, 'account.conf') # путь к файлу с аккаунтами ботов

# сообщения
MESSAGES = {
            'ACONN': 'Твой аккаунт уже подключен.\n\n',
            'INCORDATA': 'Нужно ввести команду "Вход" и логин и пароль от ОРИОКС (через пробел).\nПример: Вход 4372537 mypassword',
            'INCORDATATG': 'Введи логин и пароль от ОРИОКС (через пробел):',
            'BADPASS': 'Не удалось авторизироваться (неверные логин/пароль?)\n\n',
            'NCONN': 'Твой аккаунт не подключен.\n\n----------------\n',
            'BADINDEX': 'Неверный индекс предмета.\n\n----------------\n',
            'ORIOKSERROR': 'Не удалось получить данные. Скорее всего:\n- ОРИОКС временно недоступен.\n- Подключенный аккаунт был изменен.\n- Нужно перезайти в свой аккаунт(команды "Выход" и "Вход").',
            'LOADPROFILEERROR': 'Не удалось получить данные.\nПопробуй перезайти в свой аккаунт (команды "Выход" и "Вход").',
            'LOADDATEERROR': 'Не удалось получить текущую дату из ОРИОКС.\n',
            'NULLLOGORPASS': 'У твоего аккаунта не хватает части данных.\nПопробуй перезайти (команды "Выход" и "Вход").',
            'LOADSETTINGSERROR': 'Не удалось загрузить данные твоего аккаунта.\nПроверь, работает ли ОРОКС.',
            'OROKSNETWORKERROR': 'ОРОКС временно недоступен, попробуй повторить позже.\n\n',
            'MIETMAINNETWORKERROR': 'Сайт МИЭТ временно недоступен, попробуй повторить позже.\n\n',
            'OROKSAUTHPASSORLOGINERROR': 'У твоего аккаунта изменилась часть данных.\nПопробуй перезайти (команды "Выход" и "Вход").',
            'OROKSLOADHVPARAMERROR': 'Не удалось загрузить данные из ОРОКС.\n',

            'LOGO': 'OpenOrioks [BETA]\n\n'
            'Основные команды:\n'
            'Вход логин пароль - вход в аккаунт\n'
            'Выход - выход из аккаунта (отключает уведомления)\n'
            'Профиль - информация об аккаунте.\n'
            'Неделя - текущая неделя.\n'
            'Обучение - информация по предметам.\n'
            'Расписание - информация по занятиям на сегодня.\n'
            'Предмет n - выбрать предмет по номеру (n)\n\n'
            }

def storeBots(func):
    global BOTS
    if getattr(func, 'type', None) is None:
        return
    BOTS.update({func.type: func})


def loadAccounts():
    Parser = configparser.ConfigParser()
    bots = []
    if not os.path.exists(VKACC_PATH):
        print('Отсутствует файл account.conf')
        return []
    Parser.read(VKACC_PATH)
    for bot_type in BOTS:
        if not (bot_type in Parser.sections()):
            continue
        params = dict(Parser[bot_type].items())
        bot = BOTS[bot_type]()
        bot.auth(**params)
        bots.append(bot)
    return bots


def loadCoookies():
    global USERDATA
    data = {}
    print('[SYS] Загрузка юзеров..')
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, 'rb') as f:
            cookies = _pickle.load(f)
        for u,c in cookies.items():
            data.update({u: Orioks(c)})
    print('[SYS] OK')
    USERDATA = data


def saveCookies():
    global USERDATA
    data = {}
    for u,o in USERDATA.items():
        cookies = o.getData()
        data.update({u: cookies})
    with open(DATA_PATH, 'wb') as f:
        _pickle.dump(data, f)
    print('[SYS] Юзеры сохранены')


def parseMessage(bot, message):
    global MESSAGES
    user = message.from_id
    text = message.text
    peer = message.peer_id
    users = [q[1] for q in USERDATA.keys()]  # уже авторизированные пользователи
    if re.match(r'вход', text, re.I | re.U):
        if user in users:
            bot.send(peer, MESSAGES['ACONN'])
            return
        data = re.findall(r'вход (\w+) (.+)', text, re.I | re.U)
        if not data:
            if bot.type == 'TG':
                bot.ready_to_login = True
                bot.send(peer, MESSAGES['INCORDATATG'])
            else:
                bot.send(peer, MESSAGES['INCORDATA'])
            return
        l, p = data[0]
        reciver = Orioks(None)
        form = reciver.getloginForm()
        if form is None:
            bot.send(peer, MESSAGES['ORIOKSERROR'])
            return
        authCode = reciver.authorize(l, p)
        if authCode == 1:
            bot.send(peer, MESSAGES['BADPASS'])
        elif authCode == 2:
            bot.send(peer, MESSAGES['ORIOKSERROR'])
        else:
            name, date = reciver.getProfile()
            USERDATA.update({(bot.type, user): reciver})
            bot.send(peer, 'Вход выполнен.\nПрофиль: %s\nДата: %s' % (name, date))
        return
    elif re.match(r'выход$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        del USERDATA[(bot.type, user)]
        bot.send(peer, 'Аккаунт удален. Уведомления отключены.')
    elif re.match(r'(профиль|аккаунт|п)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        reciver = USERDATA[(bot.type, user)]
        profile = reciver.getProfile()
        if profile is None:
            bot.send(peer, MESSAGES['ORIOKSERROR'])
            return
        name, date = profile
        bot.send(peer, 'Профиль: %s' % name)
    elif re.match(r'(неделя|дата|день|д)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        reciver = USERDATA[(bot.type, user)]
        profile = reciver.getProfile()
        if profile is None:
            bot.send(peer, MESSAGES['ORIOKSERROR'])
            return
        name, date = profile
        bot.send(peer, 'Дата: %s' % date)
    elif re.match(r'(обучение|ориокс|о)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        reciver = USERDATA[(bot.type, user)]
        try:
                table = reciver.getList()
        except Exception as e:
                print('error', e)
                table = None
        if table is None:
            bot.send(peer, MESSAGES['ORIOKSERROR'])
            return
        resp = []
        for i, dis in enumerate(table['dises'], 1):
            name = dis.get('name', '')
            bal = dis.get('grade', {}).get('b', 0)
            mbal = dis.get('mvb', 0)
            fbal = dis.get('grade', {}).get('f', 0)
            resp.append('%s. %s : %s/%s (%s)' % (i, name, bal, mbal, fbal))
        bot.send(peer, '№ Предмет : текущий/возможный(всего):\n\n%s\n\nВведи номер предмета для получения списка контрольных мероприятий.' % '\n'.join(resp))
    elif re.match(r'(предмет )?(\d+)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        num = int(re.findall(r'(предмет )?(\d+)', text, re.I | re.U)[0][1])
        reciver = USERDATA[(bot.type, user)]
        try:
                table = reciver.getList()
        except Exception as e:
                print('error', e)
                table = None
        if table is None:
            bot.send(peer, MESSAGES['ORIOKSERROR'])
            return
        m = len(table['dises'])
        if num > m or num < 1:
            bot.send(peer, MESSAGES['BADINDEX'])
            return
        resp = []
        pname = table['dises'][num - 1].get('name', '')
        prefs = table['dises'][num - 1].get('preps', [])
        form = table['dises'][num - 1].get('formControl', {}).get('name', 'неизвестно')
        prefs = ['> %s' % p['name'] for p in prefs] if prefs else ''
        for dis in table['dises'][num - 1]['segments'][0]['allKms']:
            week = dis.get('week', 0)
            fname = dis['type'].get('name', '') if dis.get('type', {}) else table['dises'][num - 1]['formControl'][
                'name']
            name = dis.get('name', '')
            name = ('(%s)' % name) if name else ''
            bal = dis.get('grade', {}).get('b', 0)
            if bal == '-': bal = 0
            mbal = dis.get('max_ball', 0)
            resp.append('%s. %s %s : %s/%s' % (week, fname, name, bal, mbal))
        bot.send(peer,
                 'Предмет: %s\nФорма контроля: %s\nПреподаватели:\n%s\n\nНеделя. Предмет: балл/возможный:\n\n%s' % (
                 pname, form, '\n'.join(prefs), '\n'.join(resp)))
    elif re.match(r'(расписание( занятий)?|пары|рсп|пры)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        reciver = USERDATA[(bot.type, user)]
        data, day, ned = reciver.getSchedule(0)
        if data == 1:
            bot.send(peer, MESSAGES['OROKSNETWORKERROR'])
        elif data == 2:
            bot.send(peer, MESSAGES['OROKSAUTHPASSORLOGINERROR'])
        elif data == 3:
            bot.send(peer, MESSAGES['OROKSLOADHVPARAMERROR'])
        elif data == 4:
            bot.send(peer, MESSAGES['OROKSLOADHVPARAMERROR'])
        elif data == 5:
            bot.send(peer, MESSAGES['LOADPROFILEERROR'])
        elif data == 6:
            bot.send(peer, MESSAGES['LOADDATEERROR'])
        elif data == 7:
            bot.send(peer, MESSAGES['LOADSETTINGSERROR'])
        elif data == 8:
            bot.send(peer, MESSAGES['NULLLOGORPASS'])
        elif data == 9:
            bot.send(peer, MESSAGES['OROKSNETWORKERROR'])
        elif data == 10:
            bot.send(peer, MESSAGES['MIETMAINNETWORKERROR'])
        else:
            pars = []
            shell = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            if not data:
                resp = 'На сегодня расписания нет.'
            else:
                parnums = [int(p[0]) for p in data.keys()]
                for i in range(1, max(parnums) + 1):
                    fmt = '%s пара' % i
                    para = data.get(fmt)
                    if not para:
                        par = '%s. Окно.\n' % i
                    else:
                        tmf = dateutil.parser.parse(para[3]['TimeFrom'])
                        tmt = dateutil.parser.parse(para[3]['TimeTo'])
                        par = '%s. %.2d:%.2d - %.2d:%.2d\n%s ( %s )\n%s\nФормат занятия - %s\n' % (
                            i, tmf.hour, tmf.minute, tmt.hour, tmt.minute, para[0], para[1], para[2], para[4]
                        )
                    pars.append(par)
                resp = '\n'.join(pars)
            bot.send(peer, '%s\n%s %s\n\n%s' % (shell, day, ned, resp))
    elif re.match(r'(завтра|зав)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        reciver = USERDATA[(bot.type, user)]
        data, day, ned = reciver.getSchedule(1)
        if data == 1:
            bot.send(peer, MESSAGES['OROKSNETWORKERROR'])
        elif data == 2:
            bot.send(peer, MESSAGES['OROKSAUTHPASSORLOGINERROR'])
        elif data == 3:
            bot.send(peer, MESSAGES['OROKSLOADHVPARAMERROR'])
        elif data == 4:
            bot.send(peer, MESSAGES['OROKSLOADHVPARAMERROR'])
        elif data == 5:
            bot.send(peer, MESSAGES['LOADPROFILEERROR'])
        elif data == 6:
            bot.send(peer, MESSAGES['LOADDATEERROR'])
        elif data == 7:
            bot.send(peer, MESSAGES['LOADSETTINGSERROR'])
        elif data == 8:
            bot.send(peer, MESSAGES['NULLLOGORPASS'])
        elif data == 9:
            bot.send(peer, MESSAGES['OROKSNETWORKERROR'])
        elif data == 10:
            bot.send(peer, MESSAGES['MIETMAINNETWORKERROR'])
        else:
            pars = []
            shell = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            if not data:
                resp = 'Завтра пар нет.'
            else:
                parnums = [int(p[0]) for p in data.keys()]
                for i in range(1, max(parnums) + 1):
                    fmt = '%s пара' % i
                    para = data.get(fmt)
                    if not para:
                        par = '%s. Окно.\n' % i
                    else:
                        tmf = dateutil.parser.parse(para[3]['TimeFrom'])
                        tmt = dateutil.parser.parse(para[3]['TimeTo'])
                        par = '%s. %.2d:%.2d - %.2d:%.2d\n%s ( %s )\n%s\nФормат занятия - %s\n' % (
                            i, tmf.hour, tmf.minute, tmt.hour, tmt.minute, para[0], para[1], para[2], para[4]
                        )
                    pars.append(par)
                resp = '\n'.join(pars)
            bot.send(peer, '%s\n%s %s\n\n%s' % (shell, day, ned, resp))

    elif re.match(r'(послезавтра|послез)$', text, re.I | re.U):
        if not (user in users):
            bot.send(peer, MESSAGES['NCONN'])
            return
        reciver = USERDATA[(bot.type, user)]
        data, day, ned = reciver.getSchedule(2)
        if data == 1:
            bot.send(peer, MESSAGES['OROKSNETWORKERROR'])
        elif data == 2:
            bot.send(peer, MESSAGES['OROKSAUTHPASSORLOGINERROR'])
        elif data == 3:
            bot.send(peer, MESSAGES['OROKSLOADHVPARAMERROR'])
        elif data == 4:
            bot.send(peer, MESSAGES['OROKSLOADHVPARAMERROR'])
        elif data == 5:
            bot.send(peer, MESSAGES['LOADPROFILEERROR'])
        elif data == 6:
            bot.send(peer, MESSAGES['LOADDATEERROR'])
        elif data == 7:
            bot.send(peer, MESSAGES['LOADSETTINGSERROR'])
        elif data == 8:
            bot.send(peer, MESSAGES['NULLLOGORPASS'])
        elif data == 9:
            bot.send(peer, MESSAGES['OROKSNETWORKERROR'])
        elif data == 10:
            bot.send(peer, MESSAGES['MIETMAINNETWORKERROR'])
        else:
            pars = []
            shell = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            if not data:
                resp = 'Послезавтра пар нет.'
            else:
                parnums = [int(p[0]) for p in data.keys()]
                for i in range(1, max(parnums) + 1):
                    fmt = '%s пара' % i
                    para = data.get(fmt)
                    if not para:
                        par = '%s. Окно.\n' % i
                    else:
                        tmf = dateutil.parser.parse(para[3]['TimeFrom'])
                        tmt = dateutil.parser.parse(para[3]['TimeTo'])
                        par = '%s. %.2d:%.2d - %.2d:%.2d\n%s ( %s )\n%s\nФормат занятия - %s\n' % (
                            i, tmf.hour, tmf.minute, tmt.hour, tmt.minute, para[0], para[1], para[2], para[4]
                        )
                    pars.append(par)
                resp = '\n'.join(pars)
            bot.send(peer, '%s\n%s %s\n\n%s' % (shell, day, ned, resp))
    else:
        bot.send(peer, MESSAGES['LOGO'])
    return

# класс для взаимодействия с orioks.miet.ru
class Orioks:
    def __init__( self, cObj ):
        self.rolechange = 'https://orioks.miet.ru/main/change-role?role_name=stud&id_group=%s' # смена прав на студента
        self.base = 'https://orioks.miet.ru/' # главная страница
        self.loginform = 'https://orioks.miet.ru/user/login' # страница входа
        self.baseform = 'https://orioks.miet.ru/student/student' # страница с журналом
        self.session = requests.Session()
        self.oroks = Oroks()
        if not (cObj is None): # загрузка данных юзера (сессия и таблица с данными)
            self.session.cookies, self.table = cObj
            l, p = self.table.get('auth', (None, None))
            if not ((l is None) or (p is None)):
                code = self.oroks.auth(l, p)
                if code != 0: print('[ORIOKS] OROKS вернул код', code)
        else:
            self.table = {'current_semestr': 0, 'dises': {}, 'sems': {}, 'auth': (None, None), 'group': None}
        self.csrf = None # параметры авторизации
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.81 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4,lv;q=0.2',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
        })

    def getData(self):
        return self.session.cookies, self.table

    def getloginForm( self ):
        try:
            data = self.session.get(self.loginform)
        except requests.RequestException:
            return None
        print('[ORIOKS]', data.url, data.status_code)
        soup = BeautifulSoup(data.text, "lxml")
        # ключ формы авторизации
        self.csrf = soup.find('form', { 'id': 'login-form' }).find('input', { 'name': '_csrf' })['value']
        if self.csrf is None:
            return None
        return 1

    def authorize( self, l=None, p=None, rep=False ):
        if rep:
            l,p = self.table.get('auth', (None, None))
            if (l is None) or (p is None):
                return 3
        try:
            # авторизация с логином и паролем
            param = { '_csrf': self.csrf, 'LoginForm[login]': l, 'LoginForm[password]': p, 'LoginForm[rememberMe]': '1' }
            data = self.session.post(self.loginform, data=param)
        except requests.RequestException:
            return 2
        print('[ORIOKS]', data.url, data.status_code)
        if not self.session.cookies.get('orioks_identity'): # сервер не вернул идентификатор -> неверные логин/пароль
            return 1
        if not rep:
            try:
                table = self.getList()
            except Exception as e:
                print('error', e)
                table = None
            if table is None: # не удалось загрузить данные пользователя (не студент или ориокс лежит)
                return 2
        self.table.update({'auth': (l, p)})
        return 0

    def getProfile( self ):
        try:
            data = self.session.get(self.base)
        except requests.RequestException:
            return None
        soup = BeautifulSoup(data.text, "lxml")
        try:
            bar = soup.find('ul', { 'class': 'navbar-right' }) # правая часть меню
            date = bar.find('li', { 'class': 'active' }).text # текущая неделя
            name = soup.find_all('a', { 'class': 'dropdown-toggle', 'href': '#' })[-1].text # ФИО
        except AttributeError:
            return None
        return [name, date.strip()]

    def saveDump(self, data):
        path = os.path.join(LOCAL_PATH, 'dumps', 'error-dump-%s.html' % time.time())
        with open(path, 'w') as dump:
            dump.write(data)

    def getList( self, recursion=False ):
        try:
            data = self.session.get(self.baseform)
        except requests.RequestException:
            return None
        soup = BeautifulSoup(data.text, "lxml")
        try:
            forang = soup.find('div', { 'id': 'forang' }).text
        except AttributeError:
            if recursion: # если этот метод вызывается рекурсивно
                self.saveDump(data.text)
                return None
            if 'Авторизация' in soup.title:
                self.getloginForm()
                self.authorize(rep=True)
                return self.getList(True)
            try: # возвращаемся на главную и ищем ссылку на изменение прав аккаунта
                check = self.session.get(self.base)
            except requests.RequestException:
                return None
            rolecheck = re.findall(r'(role_name\=stud(.*?)id_group\=(\d+))', check.text, re.I | re.U) # ищем ссылку
            if rolecheck:
                role = rolecheck[0][2] # id группы юзера
                try:
                    check = self.session.get(self.rolechange % role) # меняем права аккаунта
                except requests.RequestException:
                    return None
                print('[ORIOKS]', check.url, check.status_code)
                return self.getList(True)
            self.saveDump(data.text) # если не нашли ссылку - сохраняем дамп страницы и выходим
            return None
        usertable = json.loads(forang) # загружаем данные студента
        if isinstance(usertable['dises'], dict):
            usertable['dises'] = list(usertable['dises'].values())
            usertable['dises'].sort(key=lambda dis: dis['id'])
        self.table['dises'] = usertable['dises'] # оценки
        self.table['sems'] = usertable['sems'] # список семестров
        self.table['current_semestr'] = usertable['id_semester'] # id семестра
        #self.table['dises'][0]['grade']['b'] += 1
        return self.table

    def getSchedule(self, current = 0):
        date = self.getProfile()
        if not date:
            return 5
        date = re.search(r'(\d) (числитель|знаменатель)', date[1], re.I)
        if not date:
            return 6
        date = date.group(1, 2)
        group = self.table.get('group')
        if not group:
            l, p = self.table.get('auth', (None, None))
            params = self.oroks.getSettings()
            if params == 1:
                if not ((l is None) or (p is None)):
                    code = self.oroks.auth(l, p)
                    if code != 0: return code
                else:
                    return 8
                params = self.oroks.getSettings()
                if params in [1,2]:
                    return 7
            elif params == 2:
                return 9
            group = params[1]
            self.table.update({'group': group})
            
        daynum = int(datetime.datetime.now().strftime('%w'))

        day = str(date[0])
        ned = str(date[1])

        if current == 1:
            if daynum == 0:
                daynum = 1
                
                if day == "2" and ned == "знаменатель":
                    day = "1"
                    ned = "числитель"
                elif day == "1" and ned == "числитель":
                    day = "1"
                    ned = "знаменатель"
                elif  day == "1" and ned == "знаменатель":
                    day = "2"
                    ned = "числитель"
                elif day == "2" and ned == "числитель":
                    day = "2"
                    ned = "знаменатель"
                else:
                    return 10
            else:
                daynum += 1

        if current == 2:
            if daynum == 6:
                daynum = 1
                
                if day == "2" and ned == "знаменатель":
                    day = "1"
                    ned = "числитель"
                elif day == "1" and ned == "числитель":
                    day = "1"
                    ned = "знаменатель"
                elif  day == "1" and ned == "знаменатель":
                    day = "2"
                    ned = "числитель"
                elif day == "2" and ned == "числитель":
                    day = "2"
                    ned = "знаменатель"
                else:
                    return 10
        
            else:
                daynum += 2

        schedule = Schedule([day, ned], group, daynum)
        
        if schedule.load() == 0:
            return 10
        return schedule.parse(day, ned)

# класс для взаимодействия с miet.ru/schedule
class Schedule:

    def __init__(self, dayindex, group, daynum):
        self.table = None
        self.group = group
        self.dayindex = dayindex
        self.daynum = daynum
        self.load()

    def load(self):
        url = 'https://miet.ru/schedule/data'
        try:
            raw = requests.post(url, data={'group': self.group})
        except requests.RequestException as e:
            print('[SCHEDULE] Не удалось загрузить распиание', self.group, ':', e)
            return 0
        self.table = json.loads(raw.text)
        return 1

    def parse(self, day1, ned):
        table = {'10': 0, '11': 1, '20': 2, '21': 3, '22': 4}
        day = self.daynum
        dayindex = self.dayindex
        daypair = '1' if dayindex[1] == 'знаменатель' else '0'
        dayindex = dayindex[0] + daypair
        pars = {}
        timed = lambda P: P['Day'] == day and P['DayNumber'] == table[dayindex]
        #print(day, table[dayindex])
        for para in filter(timed, self.table['Data']):
            key = para['Time']['Time'].strip()
            if para['Class']['Form'] == "":
                para['Class']['Form'] = "Очное"
            data = [para['Class']['Name'], para['Room']['Name'], para['Class']['TeacherFull'], para['Time'], para['Class']['Form']]
            if key in pars:
                pars[key][1] += ' / ' + data[1]
            else:
                pars.update({key: data})
        #pars.sort(key = lambda par: par['Time']['Code'])
        # for para in sorted(pars.items(),key=lambda p: p[0]):
        #     print(para)
        return pars, day1, ned

# класс для взаимодействия с emirs.miet.ru
class Oroks:

    def __init__(self):
        self.mainform = 'http://emirs.miet.ru/oroks-miet/scripts/login.pl?reset=1&DBnum=49'
        self.loginform = 'http://emirs.miet.ru/oroks-miet/scripts/login.pl'
        self.session = requests.Session()
        self.hidden = None
        self.settingshv = None
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4,lv;q=0.2',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36',
        })

    def getForm(self):
        try:
            data = self.session.get(self.mainform)
        except requests.RequestException:
            print('[OROKS] Не удалось получить форму входа.')
            return 1
        soup = BeautifulSoup(data.text, 'lxml')
        hidden = soup.find('input', {'type': 'hidden', 'name': 'hidden'}).get('value')
        self.hidden = hidden
        return 0

    def auth(self, l, p):
        if self.getForm() == 1:
            return 4
        form = {'hidden': self.hidden, 'ulogin': l, 'upass': p, 'enter': r'%C2%EE%E9%F2%E8'}
        try:
            data = self.session.post(self.loginform, data=form)
        except requests.RequestException:
            print('[OROKS] Не удалось отправить запрос на авторизацию.')
            return 1
        if not data.cookies.get('SUID'):
            print('[OROKS] Не удалось авторизироваться.')
            return 2
        hv = re.search(r'automenu=2&hv=(.+)\'', data.text, re.I)
        if not hv:
            print('[OROKS] Не удалось найти HV параметр. '+ data.text)
            return 3
        self.settingshv = hv.group(1)
        return 0

    def getSettings(self):
        if not self.settingshv:
            print('[OROKS] Параметр HV не определен!')
            return 1
        form = {'hv': self.settingshv, 'sw': ''}
        try:
            data = self.session.get(self.loginform, params=form)
        except requests.RequestException:
            print('[OROKS] Не удалось получить настройки.')
            return 2
        soup = BeautifulSoup(data.text, 'lxml')
        userdata = [q.text for q in soup.find_all('i')]
        if len(userdata) != 6:
            return 2
        return userdata[:3]

# класс рассылки обновлений
class UpdateTimer(threading.Thread):
    def __init__(self, bots):
        threading.Thread.__init__(self)
        self.daemon = True
        self.bots = bots

    def getBot(self, tp):
        for bot in self.bots:
            if bot.type == tp:
                return bot
        return None

    def checkUpdates(self):
        for user, reciver in USERDATA.items():
            bot = self.getBot(user[0]) # получаем тип бота согласно типу юзера
            if bot is None:
                print('[UPDATER] Тип бота не определен для', user)
                continue
            now = datetime.datetime.now()
            print('[UPDATER] [%.2d:%.2d:%.2d] Проверка обновлений для:' % (now.hour, now.minute, now.second), user)
            lst = copy.deepcopy(reciver.table) # прежнее состояние таблицы до проверки
            semCur = lst['current_semestr']
            try:
                newlist = reciver.getList()
            except Exception as e:
                print('error', e)
                newlist = None

            if newlist is None:
                print('[UPDATER] !Не удалось проверить обновления')
                continue
            semNew = newlist['current_semestr']
            if semCur != semNew: # сравниваем семестры (иначе проверка не имеет смысла)
                print('[UPDATER] !Разные значения семестров, сравнение отменяется.', semCur, semNew)
                reciver.table.update({'group': None})
                continue
            if isinstance(lst['dises'], dict):
                lst['dises'] = list(lst['dises'].values())
                lst['dises'].sort(key=lambda dis: dis['id'])
            for i, cur in enumerate(lst['dises']):
                name = cur.get('name', '') # название предмета
                balCur = cur.get('grade', { }).get('f', 0) # текущие быллы
                balNew = newlist['dises'][i].get('grade', {}).get('f', 0) # новые баллы
                if balCur == balNew:
                    continue
                #print('-', name, 'баллы:', balCur, balNew)
                print('[UPDATER] Отправка уведомления ->', user)
                bot.send(user[1], 'Изменены баллы (%s): %s -> %s' % (name, balCur, balNew))
                time.sleep(10) # ждем 10 секунд до отправки нового уведомления (для избежания флуда)

    def run(self):
        self.main()

    def main(self):
        print('[UPDATER] Демон уведомлений запущен.')
        while True:
            try:
                with LOCK:
                    self.checkUpdates()
                    saveCookies()
                print('-' * 42)
            except Exception as e:
                print('error', e)
            time.sleep(600) # ждем 15 минут до следующей проверки


#класс бота для ВК
@storeBots
class VkBot(threading.Thread):

    type = 'VK'

    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.session = None
        self.API = None
        self.group_id = None

    def auth(self, token = None, group_id = None):
        self.group_id = group_id
        print('[VK] Пробую авторизироваться ' )
        try:
            session = vk_api.VkApi(token=token)
        except vk_api.ApiError: 
            print('[VK] Не удалось авторизироваться')
            return
        self.session = session

    def run(self):
        if self.session is None: return
        self.API = self.session.get_api()
        print('[VK] VK бот запущен.')
        while True:
            try:
                self.receiveMessages()
            except Exception as e:
                print('error', e)

    def receiveMessages(self):
        LongPoll = VkBotLongPoll(self.session, self.group_id)
        for event in LongPoll.listen():
                        if event.type == VkBotEventType.MESSAGE_NEW:
                            message = collections.namedtuple('message', 'text from_id peer_id')(event.message.text, event.message.from_id, event.message.peer_id)
                            print('[VK] Новое сообщение: %s -> %s' % (message.peer_id, message.text))
                            self.typing(message.peer_id)
                            with LOCK:
                                parseMessage(self, message)

    def typing(self, i):
        try:
            self.API.messages.setActivity(peer_id=i, type='typing')
        except vk_api.ApiError as ae:
            print('[VK] !Не удалось установить статус набора: [%s] %s' % (i, ae))

    def send(self, user, text):
        try:
            print('[VK] Отправка сообщения: -> %s' % user)
            self.API.messages.send(random_id=get_random_id(), peer_id=user, message=text, keyboard=open("keyboard.json", "r", encoding="UTF-8").read())
        except vk_api.ApiError as ae:
            print('[VK] !Не удалось отправить сообщение: [%s] %s' % (user, ae))

#класс бота для TG
@storeBots
class TgBot(threading.Thread):

    type = 'TG'

    def __init__( self ):
        threading.Thread.__init__(self)
        self.daemon = True
        self.session = None
        self.ready_to_login = False
        self.markup = telebot.types.ReplyKeyboardMarkup()
        u1 = telebot.types.KeyboardButton('Вход')
        u2 = telebot.types.KeyboardButton('Выход')
        d1 = telebot.types.KeyboardButton('Профиль')
        d2 = telebot.types.KeyboardButton('Неделя')
        d3 = telebot.types.KeyboardButton('Обучение')
        t1 = telebot.types.KeyboardButton('Расписание')
        t2 = telebot.types.KeyboardButton('Завтра')
        t3 = telebot.types.KeyboardButton('Послезавтра')

        self.markup.row(u1, u2)
        self.markup.row(d1, d2, d3)
        self.markup.row(t1, t2, t3)

    def auth(self, token = None):
        print('[TG] Пробую авторизироваться с %s' % token)
        bot = telebot.TeleBot(token)
        try:
            bot.get_me()
        except telebot.apihelper.ApiException:
            print('[TG] Не удалось авторизироваться с %s' % token)
            return
        self.session = bot

    def run(self):
        if self.session is None: return
        print('[TG] TG бот запущен.')
        self.session.add_message_handler({
            'function': self.events,
            'filters': {'content_types': ['text']}
        })
        self.listen()

    def listen(self):
            while True:
                try:
                    self.session.polling(none_stop=False)
                except:
                    continue

    def send(self, user, message):
        try:
            print('[TG] Отправка сообщения: -> %s' % user)
            self.session.send_message(user, message, reply_markup=self.markup)
        except telebot.apihelper.ApiException as ae:
            print('[TG] !Не удалось отправить сообщение: [%s] %s' % (user, ae))

    def typing(self, i):
        try:
            self.session.send_chat_action(i, 'typing')
        except telebot.apihelper.ApiException as ae:
            print('[TG] !Не удалось установить статус набора: [%s] %s' % (i, ae))

    def events(self, event):
        print('[TG] Новое сообщение: %s -> %s' % (event.text, event.chat.id))
        if self.ready_to_login:
            event.text = 'Вход %s' % event.text.strip()
            self.ready_to_login = False
        message = collections.namedtuple('message', 'text from_id peer_id')(event.text, event.from_user.id, event.chat.id)
        self.typing(message.peer_id)
        with LOCK:
            parseMessage(self, message)
            



def main():
    bots = loadAccounts()
    for bot in bots:
        if bot.session is None:
            continue
        bot.start()
    UpdateTimer(bots).start()
    for bot in bots:
        if not bot.is_alive():
            continue
        bot.join()

if __name__ == '__main__':
    loadCoookies()
    try:
        main()
    except KeyboardInterrupt:
        print('\r[SYS] Выход')
        sys.exit(1)
    except BaseException as e:
        print('\r[SYS] Выход: %s:%s' % (e, traceback.format_exc()))
    saveCookies()
