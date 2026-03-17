# Tracker


```
docker compose up -d
python3 LogServer/main.py
python3 LogWorker/main.py
python3 WebApp/app.py
```


## Kibana

- Stack Management > Data views
  - Create Data View
    - Name : selenium_events
    - Index pattern : selenium-events*
    - Timestamp field : @timestamp
- Discover
  - Filters
    - `raw : "*\"found\":false*"`
