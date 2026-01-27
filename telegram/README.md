# tg_bot_best_pattern

Пользователь не появляется в базе Pasarguard пока не получит ключ. До этого он он будет находиться только в базе Бота. 

### Способы получить ключ: 
- [trial_days.py](handlers/user/trial_days.py) юзер может получить тестовый ключ.
- [user_buy.py](handlers/user/user_buy.py) покупка ключа.
- [start.py](handlers/start.py) запустить бота с диплинком, тогда в pasarguard сразу создастся новый пользователь с активноый подпиской.