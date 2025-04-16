import requests, base64, json, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "7371624181:AAHYjEBP_zc7nUV9LK4aGPDswMpUweoGzSk"
CHANNEL_ID = "-1002561863718"

# Global session with retries and connection pooling
session = requests.Session()
retries = requests.packages.urllib3.util.retry.Retry(
    total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504]
)
session.mount("https://", requests.adapters.HTTPAdapter(max_retries=retries))

def get_org_details(org_code):
    try:
        r = session.get(
            f"https://api.classplusapp.com/v2/orgs/{org_code}",
            headers={"Accept": "application/json", "User-Agent": "YourAppName/1.0"}
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "success":
            return data["data"].get("orgId"), data["data"].get("orgName")
    except Exception as e:
        print(f"Error fetching org details: {e}")
    return None, None

def update_base_url(org_id):
    base_url = "https://api.classplusapp.com/v2/course/preview/diy/similar/eyJ0dXRvcklkIjpudWxsLCJvcmdJZCI6bnVsbCwiY2F0ZWdvcnlJZCI6bnVsbH0"
    try:
        b64 = base_url.rsplit('/', 1)[-1]
        b64 += '=' * ((4 - len(b64) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(b64).decode())
        data['orgId'] = org_id
        new_b64 = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode().rstrip("=")
        return base_url.rsplit('/', 1)[0] + '/' + new_b64
    except Exception as e:
        print(f"Error updating base URL: {e}")
    return None

def update_similar_url(org_id):
    base_similar_url = ("https://api.classplusapp.com/v2/course/preview/similar/"
                        "eyJ0dXRvcklkIjpudWxsLCJvcmdJZCI6Mjk0NTAxLCJjYXRlZ29yeUlkIjpudWxsfQ=="
                        "?filterId=[1]&sortId=[7]&subCatList=&mainCategory=0&limit=10000&offset=")
    prefix = "https://api.classplusapp.com/v2/course/preview/similar/"
    try:
        b64_part = base_similar_url[len(prefix):].split('?')[0]
        query = base_similar_url.split('?', 1)[1]
        b64_padded = b64_part + '=' * ((4 - len(b64_part) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(b64_padded).decode())
        data['orgId'] = org_id  # update with the provided org id
        new_b64 = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode().rstrip("=")
        return prefix + new_b64 + "?" + query
    except Exception as e:
        print(f"Error updating similar URL: {e}")
    return base_similar_url

def transform_url(url):
    # Process the URL with various rules
    if url.startswith("https://cpvideocdn.testbook.com/streams/") and url.endswith("/thumbnail.png"):
        code = url.split("/streams/")[1].split("/")[0]
        final_url = f"https://cpvod.testbook.com/{code}/playlist.m3u8"
    elif "snapshots" in url:
        code = url.split("snapshots")[0].split("/")[-2]
        final_url = f"https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/{code}/master.m3u8"
    elif url.endswith(".jpeg"):
        code = url.split("/")[-1].split(".jpeg")[0]
        final_url = f"https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/b08bad9ff8d969639b2e43d5769342cc62b510c4345d2f7f153bec53be84fe35/{code}/master.m3u8"
    elif "/wv/" in url:
        value = url.split("/wv/")[1].split("/")[0]
        final_url = f"https://media-cdn.classplusapp.com/drm/{value}/playlist.m3u8"
    elif ".com/" in url:
        segment = url.split(".com/")[1].split("/")[0]
        if len(segment) in [4, 5, 6]:
            final_url = url.replace("/thumbnail.png", "/master.m3u8")
        else:
            final_url = url
    elif url.endswith("/thumbnail.jpg"):
        final_url = url.replace("/thumbnail.jpg", "/master.m3u8")
    else:
        final_url = url

    return final_url

def fetch_json(url):
    try:
        r = session.get(url)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

def fetch_content(base_url, folder_id):
    try:
        r = session.get(base_url.replace("folderId=0", f"folderId={folder_id}"))
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error fetching content for folderId {folder_id}: {e}")
    return None

# --- Helper functions for combining names with overlap removal ---

blacklist = {"video", "video classes", "video class", "subject wise content", "video lectures", "video lecture"}

def longest_overlap(a, b):
    max_overlap = ""
    max_len = min(len(a), len(b))
    for i in range(1, max_len + 1):
        if a[-i:] == b[:i]:
            max_overlap = a[-i:]
    return max_overlap

def combine_names(names):
    result = []
    n = len(names)
    for i in range(n):
        current = names[i].strip()
        if current.lower() in blacklist:
            continue
        if i < n - 1:
            next_name = names[i + 1].strip()
            ovl = longest_overlap(current, next_name)
            if ovl and ovl == current:
                continue
            cleaned = current[:-len(ovl)].rstrip() if ovl else current
            if cleaned:
                result.append(cleaned)
        else:
            result.append(current)
    return " ".join(result)

def process_folders_iter(base_url, folder_tuples, output_file, executor):
    while folder_tuples:
        new_tuples = []
        future_to_tuple = {executor.submit(fetch_content, base_url, folder_id): (folder_id, name_list)
                           for folder_id, name_list in folder_tuples}
        for future in as_completed(future_to_tuple):
            folder_id, parent_names = future_to_tuple[future]
            data = future.result()
            if data:
                for item in data.get('data', []):
                    current_name = item.get('name', '').strip()
                    new_names = parent_names.copy()
                    if current_name:
                        new_names.append(current_name)
                    videos = item.get('resources', {}).get('videos', 0)
                    if videos == 0 and item.get('thumbnailUrl'):
                        hierarchical_name = combine_names(new_names)
                        output_file.write(f"{hierarchical_name} : {transform_url(item.get('thumbnailUrl'))}\n")
                    elif videos > 0:
                        new_tuples.append((item.get('id'), new_names))
        folder_tuples = new_tuples

def get_initial_folder_ids(base_url):
    data = fetch_json(base_url)
    if data:
        return [(item['id'], [item.get('name', '').strip()]) for item in data.get('data', [])
                if item.get('resources', {}).get('videos', 0) > 0 and item.get('name')]
    return []

def decode_b64(encoded):
    try:
        encoded += '=' * ((4 - len(encoded) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(encoded).decode())
    except Exception as e:
        print(f"B64 decode error: {e}")
    return {}

def encode_b64(data):
    return base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode().rstrip("=")

def process_triplet(base_url, org_id, course_id, file_name, org_name):
    part = base_url.split("/list/")[1].split("?")[0]
    data = decode_b64(part)
    data['courseId'] = course_id
    data['orgId'] = org_id
    new_part = encode_b64(data)
    updated_url = base_url.replace(part, new_part)
    print(f"Updated URL for orgId: {org_id}, courseId: {course_id} : {updated_url}")
    
    # Fetch the full JSON data from the updated URL (folderId=0)
    base_data = fetch_json(updated_url)
    if not base_data:
        print("No data available from the updated base URL.")
        return

    safe_name = re.sub(r'[<>:"/\\|?*]', '_', file_name)
    file_path = f'/⁨Files/On My iPhone/txt group⁩/{safe_name}.txt'
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, 'w') as f:
        # Process top-level items that have a thumbnail URL (even if not folders)
        for item in base_data.get('data', []):
            if item.get('thumbnailUrl') and item.get('resources', {}).get('videos', 0) == 0:
                name = item.get('name', '').strip()
                f.write(f"{name} : {transform_url(item.get('thumbnailUrl'))}\n")
        
        # Then process folder items (those with videos > 0) recursively
        folder_tuples = [(item['id'], [item.get('name', '').strip()])
                         for item in base_data.get('data', [])
                         if item.get('resources', {}).get('videos', 0) > 0 and item.get('name')]
        if folder_tuples:
            with ThreadPoolExecutor(max_workers=20) as executor:
                process_folders_iter(updated_url, folder_tuples, f, executor)
                
    print(f"Output saved to {file_path}")
    if os.path.getsize(file_path) > 0:
        send_file(file_path, file_name, org_name)
    else:
        print(f"File {file_path} is empty.")
    os.remove(file_path)
    print(f"File {file_path} deleted.")

def send_file(file_path, course_name, coaching_name):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    caption = f"COURSE NAME - {course_name}\nCOACHING - {coaching_name}"
    with open(file_path, 'rb') as f:
        try:
            r = session.post(url, data={'chat_id': CHANNEL_ID, 'caption': caption}, files={'document': f})
            res = r.json()
            if res.get('ok'):
                print("File sent successfully to Telegram.")
            else:
                print(f"Telegram error: {res.get('description')}")
        except Exception as e:
            print(f"Error sending file: {e}")

if __name__ == "__main__":
    org_code = input("Enter org code: ")

    org_id, org_name = get_org_details(org_code)
    if org_id and org_name:
        updated_base = update_base_url(org_id)
        if updated_base:
            print(f"Updated Base URL: {updated_base}")
            courses = fetch_json(updated_base)
            if courses:
                displayed = set()
                triplets = []
                serial = 1
                print("Available courses:")
                sections = ['popular', 'recent', 'feature', 'all', 'upcomingLiveClasses']
                for sec in sections:
                    sec_data = courses.get('data', {}).get(sec, {})
                    for course in sec_data.get('coursesData', []):
                        cid = course.get('id')
                        if course.get('orgId') and cid and course.get('name') and cid not in displayed:
                            print(f"{serial}. {course.get('name')} : {cid}")
                            displayed.add(cid)
                            triplets.append((course.get('orgId'), cid, course.get('name').replace(' ', '_')))
                            serial += 1
                similar_url = update_similar_url(org_id)
                similar_courses = fetch_json(similar_url)
                if similar_courses:
                    similar_list = similar_courses.get('data', {}).get('coursesData', [])
                    for course in similar_list:
                        cid = course.get('id')
                        if course.get('orgId') and cid and course.get('name') and cid not in displayed:
                            print(f"{serial}. {course.get('name')} : {cid}")
                            displayed.add(cid)
                            triplets.append((course.get('orgId'), cid, course.get('name').replace(' ', '_')))
                            serial += 1
                if not triplets:
                    print("No courses found.")
                else:
                    sel = input("Enter the serial number(s) to process (e.g., 1,2,3 or 'all'): ").strip()
                    base_url = "https://api.classplusapp.com/v2/course/preview/content/list/eyJjb3Vyc2VJZCI6IjUzNDY4NyIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo3NjMzMjAsImNhdGVnb3J5SWQiOm51bGx9?folderId=0&limit=10000&offset=0"
                    if sel.lower() == "all":
                        print("Processing all courses simultaneously...")
                        with ThreadPoolExecutor(max_workers=20) as executor:
                            futures = [executor.submit(process_triplet, base_url, trip[0], trip[1], trip[2], org_name)
                                       for trip in triplets]
                            for fut in as_completed(futures):
                                fut.result()
                    else:
                        for i in sel.split(','):
                            try:
                                idx = int(i.strip()) - 1
                                if 0 <= idx < len(triplets):
                                    process_triplet(base_url, *triplets[idx], org_name)
                                else:
                                    print(f"Serial number {i.strip()} is out of range.")
                            except ValueError:
                                print(f"Invalid input: {i.strip()}")
            else:
                print("Failed to fetch courses from the updated base URL.")
        else:
            print("Failed to update base URL.")
    else:
        print("Invalid org code.")