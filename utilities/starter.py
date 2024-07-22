from utilities.vertus import Vertus
from random import uniform
from data import config
from utilities.core import logger
import asyncio
from aiohttp.client_exceptions import ContentTypeError
from utilities.telegram import Accounts
import datetime
import pandas as pd
import os


async def vertusStart(thread: int, session_name: str, phone_number: str, proxy: [str, None]):
    await asyncio.sleep(uniform(*config.DELAYS['ACCOUNT']))
    vertus = await Vertus.create(session_name=session_name, phone_number=phone_number, thread=thread, proxy=proxy)
    account = session_name + '.session'

    if await vertus.login():
        logger.success(f"Vertus | Thread {thread} | {account} | Login")
        while True:
            try:
                data = await vertus.get_data()

                if not await vertus.is_activated(data):
                    wallet = await vertus.create_wallet()
                    logger.success(f"Vertus | Thread {thread} | {account} | Create wallet: {wallet}")

                if await vertus.can_collect_first(data):
                    amount = await vertus.first_collect()
                    logger.success(f"Vertus | Thread {thread} | {account} | First collect {amount} VERT")

                if vertus.can_claim_daily_reward(data):
                    status, claim_count = await vertus.claim_daily_reward()
                    if status == 201:
                        logger.success(f"Vertus | Thread {thread} | {account} | Claim daily reward: {claim_count} VERT!")
                    else:
                        logger.error(f"Vertus | Thread {thread} | {account} | Can't claim daily reward! Response {status}")

                await vertus.complete_all_missions(await vertus.missions_check())

                await asyncio.sleep(5)
                
                storage = vertus.get_storage(data)

                if storage >= 0.003:
                    status, balance = await vertus.collect()
                    if status == 201:
                        logger.success(f"Vertus | Thread {thread} | {account} | Collect VERT! New balance: {balance}")
                    else:
                        logger.error(f"Vertus | Thread {thread} | {account} | Can't collect VERT! Response {status}")
                        continue

                balance = vertus.get_balance(data)
                farm, population = vertus.get_upgrades(data)

                if farm is None or farm > 10: farm = 9999
                if population is None or population > 10: population = 9999

                if farm < population and balance >= farm:
                    upgrade = "farm"
                elif farm > population and balance >= population:
                    upgrade = "population"
                elif farm == population and balance >= population:
                    upgrade = "farm"
                else:
                    upgrade = ""

                if upgrade:
                    status, balance = await vertus.upgrade(upgrade)
                    if status == 201:
                        logger.success(f"Vertus | Thread {thread} | {account} | Upgrade {upgrade}! New balance: {balance}")
                    else:
                        logger.error(f"Vertus | Thread {thread} | {account} | Can't upgrade {upgrade}! Response {status}")

                cards = None
                while True:
                    await asyncio.sleep(uniform(*config.DELAYS['BUY_CARD']))
                    card = await vertus.get_profitable_upgrade_card(balance, cards)
                    if not card: break

                    status, balance, cards = await vertus.buy_upgrade_card(card['id'])
                    if status == 201:
                        logger.success(f"Vertus | Thread {thread} | {account} | Buy card «{card['title']}» in «{card['category']}»! New balance: {balance}")
                    else:
                        logger.error(f"Vertus | Thread {thread} | {account} | Can't buy card «{card['title']}» in «{card['category']}»! Response {status}: {balance}")

                await asyncio.sleep(uniform(*config.DELAYS['REPEAT']))
            except ContentTypeError as e:
                logger.error(f"Vertus | Thread {thread} | {account} | Error: {e}")
                await asyncio.sleep(15)

            except Exception as e:
                logger.error(f"Vertus | Thread {thread} | {account} | Error: {e}")
                await asyncio.sleep(10)

    else:
        await vertus.logout()


async def vertusStats():
    accounts = await Accounts().get_accounts()
    tasks = []
    for thread, account in enumerate(accounts):
        session_name, phone_number, proxy = account.values()
        # Создаем экземпляр Vertus, используя метод create
        vertus_instance = await Vertus.create(thread=thread, session_name=session_name, phone_number=phone_number, proxy=proxy)
        # Добавляем задачу вызова stats() для созданного экземпляра
        tasks.append(asyncio.create_task(vertus_instance.stats()))
    
    data = await asyncio.gather(*tasks)
    path = f"statistics/statistics_{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.csv"
    columns = ['Registered', 'Phone number', 'Name', 'Balance', 'Referrals', 'Referral link', 'Wallet', 'Proxy (login:password@ip:port)']
    if not os.path.exists('statistics'): os.mkdir('statistics')
    df = pd.DataFrame(data, columns=columns)
    df.to_csv(path, index=False, encoding='utf-8-sig')
    logger.success(f"Saved statistics to {path}")