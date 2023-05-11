import pandahouse

connection = {'host': 'https://clickhouse.lab.karpov.courses',
                      'database':'simulator_20230320',
                      'user':'student',
                      'password':'dpo_python_2020'
                     }

q = 'SELECT * FROM {db}.feed_actions where toDate(time) = today() limit 10'

df = pandahouse.read_clickhouse(q, connection=connection)

print(df.head())
