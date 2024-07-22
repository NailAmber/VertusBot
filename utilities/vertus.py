import random
import time
from datetime import datetime
from utilities.core import logger
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView
import asyncio
from urllib.parse import unquote, quote
from data import config
import aiohttp
from fake_useragent import UserAgent
from aiohttp_socks import ProxyConnector
import json
import os


class Vertus:
    def __init__(self, thread: int, session_name: str, phone_number: str, proxy: [str, None]):
        self.account = session_name + '.session'
        self.thread = thread
        self.proxy = f"{config.PROXY_TYPES['REQUESTS']}://{proxy}" if proxy is not None else None
        self.user_agent_file = "./sessions/user_agents.json"
        self.statistics_file = "./statistics/stats.json"
        self.ref_link_file = "./sessions/ref_links.json"

        if proxy:
            proxy = {
                "scheme": config.PROXY_TYPES['TG'],
                "hostname": proxy.split(":")[1].split("@")[1],
                "port": int(proxy.split(":")[2]),
                "username": proxy.split(":")[0],
                "password": proxy.split(":")[1].split("@")[0]
            }

        with open("./data/api_config.json", "r") as f:
            apis = json.load(f)
            phone_number = apis[phone_number]
            api_id = phone_number[0]
            api_hash = phone_number[1]


        self.client = Client(
            name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            workdir=config.WORKDIR,
            proxy=proxy,
            lang_code="ru"
        )

        

    async def init_async(self, proxy):
        self.refferal_link = await self.get_ref_link()
        user_agent = await self.get_user_agent()
        headers = {'User-Agent': user_agent}
        connector = ProxyConnector.from_url(self.proxy) if proxy else aiohttp.TCPConnector(verify_ssl=False)
        self.session = aiohttp.ClientSession(headers=headers, trust_env=True, connector=connector, timeout=aiohttp.ClientTimeout(120))
        self.initialized = True


    @classmethod
    async def create(cls, thread: int, session_name: str, phone_number: str, proxy: [str, None]):
        instance = cls(session_name=session_name, phone_number=phone_number, thread=thread, proxy=proxy)
        await instance.init_async(proxy)
        return instance
    

    async def get_ref_link(self):
        ref_links = await self.load_ref_links()
        if self.account in ref_links:
            if "Vertus" in ref_links[self.account]:
                return ref_links[self.account]["Vertus"]
        else:
            return None


    async def load_ref_links(self):
        if os.path.exists(self.ref_link_file):
            with open(self.ref_link_file, "r") as f:
                return json.load(f)
        else:
            return {}
        
    
    async def save_ref_links(self, ref_links):
        os.makedirs(os.path.dirname(self.ref_link_file), exist_ok=True)
        with open(self.ref_link_file, "w") as f:
            json.dump(ref_links, f, indent=4)


    async def referrals_check(self, resp_json):
            if self.refferal_link is None:
                ref_links = await self.load_ref_links()
                if self.account not in ref_links:
                    ref_links[self.account] = {"Vertus": resp_json["data"]["user"]["referralCode"]}
                else:
                    Altooshka_ref = ref_links[self.account] 
                    Altooshka_ref["Vertus"] = resp_json["data"]["user"]["referralCode"]
                await self.save_ref_links(ref_links)


    async def get_user_agent(self):
        user_agents = await self.load_user_agents()
        if self.account in user_agents:
            return user_agents[self.account]
        else:
            new_user_agent = UserAgent(os='ios').random
            user_agents[self.account] = new_user_agent
            await self.save_user_agents(user_agents)
            return new_user_agent
        

    async def load_user_agents(self):
        if os.path.exists(self.user_agent_file):
            with open(self.user_agent_file, "r") as f:
                return json.load(f)
        else:
            return {}
        

    async def save_user_agents(self, user_agents):
        os.makedirs(os.path.dirname(self.user_agent_file), exist_ok=True)
        with open(self.user_agent_file, "w") as f:
            json.dump(user_agents, f, indent=4)

    
    async def missions_check(self):
        resp = await self.session.post('https://api.thevertus.app/missions/get')
        resp_json = await resp.json()
        return resp_json
    
    async def complete_all_missions(self, missions):
        for i in range(len(missions["groups"])):
            for mission in missions["groups"][i]["missions"][0]:
                await self.complete_mission(mission)
        for i in range(len(missions["sponsors"])):
            for mission in missions["sponsors"][i]:
                await self.complete_mission(mission)
        for mission in missions["community"][0]:
            await self.complete_mission(mission)

    async def complete_mission(self, mission):
        if not mission['title'] in config.BLACKLIST_TASK and mission['isCompleted'] == False:
            if 'link' in mission and 'https://t.me/' in mission['link'] and mission['type'] == 'REGULAR' and mission['resource'] == 'TELEGRAM':
                await self.client.connect()
                try:
                    if '+' in mission['link']:
                        await self.client.join_chat(mission['link'])
                    else:
                        await self.client.join_chat(mission['link'].split('/')[3])
                except Exception as e:
                    print("e = ", e)
                await self.client.disconnect()
                
                await asyncio.sleep(1)

                resp = await self.session.post('https://api.thevertus.app/missions/check-telegram', json={'missionId': mission['_id']})
            else:
                resp = await self.session.post('https://api.thevertus.app/missions/complete', json={'missionId': mission['_id']})
            # try:
                # resp_json = await resp.json()
                # print(mission['title'], resp_json['message'])
            # except Exception as e:
                # print('e = ', e)
            await asyncio.sleep(5)
            

    async def buy_upgrade_card(self, card_id: str):
        resp = await self.session.post('https://api.thevertus.app/upgrade-cards/upgrade', json={'cardId': card_id})
        resp_json = await resp.json()

        return resp.status, self.from_nano(resp_json.get('balance')) if resp_json.get("isSuccess") else await resp.text(), resp_json.get('cards')

    async def get_profitable_upgrade_card(self, balance, upgrade_cards: [dict, None] = None):
        if upgrade_cards:
            upgrade_cards = upgrade_cards.get('economyCards') + upgrade_cards.get('militaryCards') + upgrade_cards.get('scienceCards')
        else:
            upgrade_cards = await self.get_upgrades_cards()

        cards = []
        for card in upgrade_cards:
            if not card['isLocked'] and card['isUpgradable'] and self.from_nano(card['levels'][card['currentLevel']]['cost']) <= balance and card['currentLevel'] <= config.VERTUS_UPRGADE_LVL:
                cards.append({
                    "id": card['_id'],
                    "profitability": card['levels'][card['currentLevel']]['value'] / card['levels'][card['currentLevel']]['cost'],
                    "title": card['cardName'],
                    "category": card['type']
                })

        return max(cards, key=lambda x: x["profitability"]) if cards else None

    async def get_upgrades_cards(self):
        resp = await self.session.get('https://api.thevertus.app/upgrade-cards')
        r = await resp.json()

        return r.get('economyCards') + r.get('militaryCards') + r.get('scienceCards')

    async def stats(self):
        await self.login()
        data = await self.get_data()

        registered = '✅' if data.get('activated') else '❌'
        balance = self.from_nano(data.get('balance'))
        wallet = data.get('walletAddress')
        referral_link = 'https://t.me/vertus_app_bot/app?startapp=' + str(data.get('telegramId'))

        referrals = (await (await self.session.post('https://api.thevertus.app/users/get-referrals/1', json={})).json()).get('total')

        await self.logout()

        await self.client.connect()
        me = await self.client.get_me()
        phone_number, name = "'" + me.phone_number, f"{me.first_name} {me.last_name if me.last_name is not None else ''}"
        await self.client.disconnect()

        proxy = self.proxy.replace(f'{config.PROXY_TYPES["REQUESTS"]}://', "") if self.proxy is not None else '-'
        return [registered, phone_number, name, str(balance), str(referrals), referral_link, wallet, proxy]

    def can_claim_daily_reward(self, data):
        if data.get("dailyRewards").get('lastRewardClaimed') is None: return True
        return self.iso_to_unix_time(data.get("dailyRewards").get('lastRewardClaimed')) + 86400 < self.current_time()

    async def claim_daily_reward(self):
        resp = await self.session.post("https://api.thevertus.app/users/claim-daily", json={})
        resp_json = await resp.json()

        return resp.status, self.from_nano(resp_json.get('claimed')) if resp_json.get("success") else await resp.text()

    async def upgrade(self, upgrade):
        json_data = {"upgrade": upgrade}
        resp = await self.session.post('https://api.thevertus.app/users/upgrade', json=json_data)
        resp_json = await resp.json()

        return resp.status, self.from_nano(resp_json.get('newBalance')) if resp_json.get("success") else await resp.text()

    async def collect(self):
        resp = await self.session.post('https://api.thevertus.app/game-service/collect', json={})
        return resp.status, self.from_nano((await resp.json()).get('newBalance')) if resp.status == 201 else await resp.text()

    def get_storage(self, data):
        return self.from_nano(data.get('vertStorage'))

    def get_balance(self, data):
        return self.from_nano(data.get('balance'))

    async def first_collect(self):
        resp = await self.session.post('https://api.thevertus.app/game-service/collect-first', json={})
        return self.from_nano((await resp.json()).get('newBalance'))

    async def get_data(self):
        resp = await self.session.post('https://api.thevertus.app/users/get-data', json={})
        return (await resp.json()).get('user')

    async def create_wallet(self):
        resp = await self.session.post('https://api.thevertus.app/users/create-wallet', json={})
        return (await resp.json()).get('walletAddress')

    @staticmethod
    def get_offline_profit(data):
        return data.get('earnedOffline')

    @staticmethod
    def get_upgrades(data):
        return data.get('abilities').get('farm').get('priceToLevelUp'), data.get('abilities').get('population').get('priceToLevelUp')

    @staticmethod
    def iso_to_unix_time(iso_time: str):
        return int(datetime.strptime(iso_time, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()) + 1

    @staticmethod
    def current_time():
        return int(time.time())


    @staticmethod
    async def can_collect_first(data):
        return not data.get('storage') and not data.get('balance')

    @staticmethod
    async def is_activated(data):
        return data.get('activated')

    @staticmethod
    def from_nano(amount: int):
        return amount/1e18

    @staticmethod
    def to_nano(amount: int):
        return amount*1e18

    async def logout(self):
        await self.session.close()

    async def login(self):
        await asyncio.sleep(random.uniform(*config.DELAYS['ACCOUNT']))
        query = await self.get_tg_web_data()

        if query is None:
            logger.error(f"Vertus | Thread {self.thread} | {self.account} | Session {self.account} invalid")
            await self.logout()
            return None

        self.session.headers['Authorization'] = 'Bearer ' + query
        return True

    async def get_tg_web_data(self):
        try:
            await self.client.connect()
            web_view = await self.client.invoke(RequestWebView(
                peer=await self.client.resolve_peer('Vertus_App_bot'),
                bot=await self.client.resolve_peer('Vertus_App_bot'),
                platform='android',
                from_bot_menu=False,
                url='https://t.me/vertus_app_bot/app'
            ))

            await self.client.disconnect()
            auth_url = web_view.url

            query = unquote(string=unquote(string=auth_url.split('tgWebAppData=')[1].split('&tgWebAppVersion')[0]))
            query_id = query.split('query_id=')[1].split('&user=')[0]
            user = quote(query.split("&user=")[1].split('&auth_date=')[0])
            auth_date = query.split('&auth_date=')[1].split('&hash=')[0]
            hash_ = query.split('&hash=')[1]

            return f"query_id={query_id}&user={user}&auth_date={auth_date}&hash={hash_}"
        except:
            return None