# Tracker


```
docker compose up -d
python LogServer/main.py
python LogWorker/main.py
python WebApp/app.py
```


## Kibana

- Stack Management > Data views
  - Create Data View
    - Name : selenium_events
    - Index pattern : selenium-events*
    - Timestamp field : @timestamp
- Discover
