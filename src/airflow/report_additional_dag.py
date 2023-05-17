import io
from datetime import datetime, timedelta
import os
import dotenv

import matplotlib.pyplot as plt
import seaborn as sns
import pandahouse as ph

import telegram

from airflow.decorators import dag, task


def report_telegram(df_new_users, df_feed, df_feed_message, df_message, chat_id):
    def new_users(df_new_users, week, yesterday):
        plt.figure(figsize=(8, 6))
        sns.lineplot(x="first_action", y="new_users", data=df_new_users, hue='source')
        plt.title('New users for ' + week + ' - ' + yesterday)
        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'new_users.png'
        plt.close()
        return plot_object

    def feed(df_feed, week, yesterday):
        plt.figure(figsize=(8, 6))
        plt.stackplot(df_feed.date, df_feed.likes, df_feed.views, df_feed.events,
                      labels=['likes', 'views', 'all events'], baseline='zero')
        plt.legend(loc='best')
        plt.xlabel('date')
        plt.ylabel('event')
        plt.title('Events for ' + week + ' - ' + yesterday)
        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'events.png'
        plt.close()
        return plot_object

    def feed_and_message(df_feed_message, week, yesterday):
        df_feed_message['date'] = df_feed_message.date.dt.strftime('%d-%m-%Y')
        # set the figure size
        plt.figure(figsize=(8, 6))
        plt.legend(ncol=3, loc="best", frameon=True)
        plt.ylabel('active users')
        plt.title('Active users for ' + week + ' - ' + yesterday)

        plot_object = io.BytesIO()
        plt.savefig(plot_object, bbox_inches='tight')
        plot_object.seek(0)
        plot_object.name = 'active_users.png'
        plt.close()
        return plot_object

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

    sns.set_style("whitegrid")

    yesterday = (datetime.today() - timedelta(days=1)).strftime('%d.%m.%Y')
    week = (datetime.today() - timedelta(days=7)).strftime('%d.%m.%Y')

    # ключевые метрики за вчера
    dau = df_feed.DAU[df_feed.shape[0] - 1]
    message = df_message.message[df_message.shape[0] - 1]
    views = df_feed.views[df_feed.shape[0] - 1]
    likes = df_feed.likes[df_feed.shape[0] - 1]
    ctr = df_feed.CTR[df_feed.shape[0] - 1]
    new = df_new_users.new_users[df_new_users.shape[0] - 1]

    # Отправка текстового сообщения
    msg = f'''Ключевые метрики за *{yesterday}*:
    *DAU* - {dau} 
    *Новые пользователи* - {new}
    *Просмотры* - {views}
    *Лайки* - {likes}
    *CTR* - {ctr}
    *Отправленные сообщения* - {message}'''
    bot.sendMessage(chat_id=chat_id, text=msg, parse_mode='Markdown')

    # Создание массива с графиками для send_media_group()
    media_group = [telegram.InputMediaPhoto(media=feed_and_message(df_feed_message, week, yesterday)),
                   telegram.InputMediaPhoto(media=new_users(df_new_users, week, yesterday)),
                   telegram.InputMediaPhoto(media=feed(df_feed, week, yesterday)),
                   telegram.InputMediaPhoto(media=create_graph(df_feed, 'CTR', yesterday, week)),
                   telegram.InputMediaPhoto(media=create_graph(df_message, 'message', yesterday, week))]

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
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2023, 4, 19),
}

# Интервал запуска DAG
schedule_interval = '0 11 * * *'


@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def report_additional_dag():
    @task()
    def extract_feed():
        q = '''
        SELECT  toDate(time) as date,
                uniq(user_id) as DAU,
                count(*) as events,
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
    def extract_message_feed():
        q = '''
        SELECT  t3.date as date,
                feed,
                message,
                feed_and_message
        FROM 
            (SELECT  t1.date as date,
                    uniq(t1.user_id) as feed_and_message
            FROM
            (SELECT  toDate(time) as date,
                    user_id
            FROM    simulator_20230320.message_actions) as t1
            LEFT SEMI JOIN
            (SELECT  toDate(time) as date,
                    user_id
            FROM    simulator_20230320.feed_actions) as t2
            ON t1.date=t2.date AND t1.user_id = t2.user_id
            GROUP BY date) t3 
        JOIN
            (SELECT  t4.date as date,
                    uniq(t4.user_id) as feed
            FROM
            (SELECT  toDate(time) as date,
                    user_id
            FROM    simulator_20230320.feed_actions) as t4
            LEFT ANTI JOIN
            (SELECT  toDate(time) as date,
                    user_id
            FROM    simulator_20230320.message_actions) as t5
            ON t4.date=t5.date AND t4.user_id = t5.user_id
            GROUP BY date) t6
        ON t3.date = t6.date
        JOIN 
            (SELECT  t8.date as date,
                    uniq(t8.user_id) as message
            FROM
            (SELECT  toDate(time) as date,
                    user_id
            FROM    simulator_20230320.feed_actions) as t7
            RIGHT ANTI JOIN
            (SELECT  toDate(time) as date,
                    user_id
            FROM    simulator_20230320.message_actions) as t8
            ON t7.date=t8.date AND t7.user_id = t8.user_id
            GROUP BY date) t9 
        ON t6.date = t9.date
        WHERE date BETWEEN today() - 7 AND  yesterday()
        '''
        df = ph.read_clickhouse(query=q, connection=connection)
        return df

    @task()
    def extract_message():
        q = '''
        SELECT  toDate(time) as date,
                count(*) as message
        FROM    simulator_20230320.message_actions
        GROUP BY date
        ORDER BY date
        '''
        df = ph.read_clickhouse(query=q, connection=connection)
        return df

    @task()
    def extract_new_users():
        q = '''
        SELECT  first_action,
                source,
                COUNT(DISTINCT user_id) AS new_users
        FROM simulator_20230320.feed_actions
        LEFT JOIN
            (SELECT MIN(toDate(time)) AS first_action,
                    user_id
            FROM simulator_20230320.feed_actions
            GROUP BY user_id) t2 USING(user_id)
        WHERE first_action BETWEEN today() - 7 AND  yesterday()
        GROUP BY first_action, source
        ORDER BY first_action
        '''
        df = ph.read_clickhouse(query=q, connection=connection)
        return df

    @task()
    def load(df_feed_message, df_feed, df_message, df_new_users):
        print('extract OK')
        report_telegram(df_new_users, df_feed, df_feed_message, df_message, chat_id=143274204)

    df_feed_message = extract_message_feed()
    df_feed = extract_feed()
    df_message = extract_message()
    df_new_users = extract_new_users()
    load(df_feed_message, df_feed, df_message, df_new_users)


report_additional_dag = report_additional_dag()
