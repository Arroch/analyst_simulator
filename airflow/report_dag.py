import io
from datetime import datetime, timedelta
import os
import dotenv

import matplotlib.pyplot as plt
import seaborn as sns
import pandahouse as ph

import telegram

from airflow.decorators import dag, task


def report_telegram(df, chat_id):
    # Сетка для графиков
    sns.set_style("whitegrid")

    # Функция для создания и сохранения графиков в буфер
    def create_graph(df, metric, yesterday, week):
        plt.figure(figsize=(8, 6))
        plt.title(metric + ' for ' + week + ' - ' + yesterday)
        sns.lineplot(x=df.date, y=df[metric])
        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = metric + '.png'
        plt.close()
        return plot_object

    bot = telegram.Bot(token=my_token)
    yesterday = (datetime.today() - timedelta(days=1)).strftime('%d.%m.%Y')
    week = (datetime.today() - timedelta(days=7)).strftime('%d.%m.%Y')
    # ключевые метрики за вчера
    dau = df.DAU[df.shape[0] - 1]
    views = df.views[df.shape[0] - 1]
    likes = df.likes[df.shape[0] - 1]
    ctr = df.CTR[df.shape[0] - 1]

    # Отправка текстового сообщения
    msg = f'''Ключевые метрики за *{yesterday}*:
    *DAU* - {dau}
    *Просмотры* - {views}
    *Лайки* - {likes}
    *CTR* - {ctr}'''
    print(msg)
    bot.sendMessage(chat_id=chat_id, text=msg, parse_mode='Markdown')

    media_group = []

    # Создание массива с графиками для send_media_group()
    for metric in df.columns[1:]:
        media_group.append(telegram.InputMediaPhoto(media=create_graph(df, metric, yesterday, week),
                                                    caption=metric + ' for ' + week + ' - ' + yesterday))
    # Отправка группы медиа
    bot.sendMediaGroup(chat_id=chat_id, media=media_group)


dotenv.load_dotenv()
connection = {'host': os.getenv('host'),
              'database': os.getenv('extract_database'),
              'user': os.getenv('extract_user'),
              'password': os.getenv('extract_password')
              }

my_token = os.getenv('my_token')

# Дефолтные параметры, которые прокидываются в таски
default_args = {
    'owner': 'r.breus',
    'depends_on_past': False,
    'retries': 5,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2023, 4, 19),
}

# Интервал запуска DAG
schedule_interval = '0 11 * * *'


@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def report_dag():
    @task()
    def extract():
        q = '''
        SELECT  toDate(time) as date,
                uniq(user_id) as DAU,
                countIf(action, action = 'view') as views,
                countIf(action, action = 'like') as likes,
                round(likes/views, 2) as CTR
        FROM simulator_20230320.feed_actions 
        WHERE date BETWEEN today() - 7 AND  yesterday() 
        GROUP BY date
        ORDER BY date
        '''
        df = ph.read_clickhouse(query=q, connection=connection)
        return df

    @task()
    def load(df):
        print('extr ok')
        report_telegram(df, chat_id=143274204)

    df = extract()
    load(df)


report_dag = report_dag()
