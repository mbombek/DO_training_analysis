import requests
from lxml import etree
import time
import re
import json
import argparse
import logging
import os

DO_URL = 'https://www.dugout-online.com'

POSITION_ATTR = ['Goalkeeper', 'Defender', 'Midfielder', 'Forward']
ENG_LABEL = {
    'Refleksi': 'Reflexes',
    'Ena na ena': 'One on ones',
    'Lovljenje žoge': 'Handling',
    'Komunikativnost': 'Communication',
    'Ekscentričnost': 'Eccentricity',
    'Vdrsavanje': 'Tackling',
    'Pokrivanje': 'Marking',
    'Igra z glavo': 'Heading',
    'Predložki': 'Crossing',
    'Kreativnost': 'Creativity',
    'Podaje': 'Passing',
    'Strel iz daljave': 'Long shots',
    'Kontrola žoge': 'First touch',
    'Strel na gol': 'Shooting',
    'Preigravanje': 'Dribbling',
    'Pozicioniranje': 'Positioning',
    'Agresivnost': 'Aggression',
    'Delavnost': 'Team work',
    'Hitrost': 'Speed',
    'Moč': 'Strength',
    'Vpliv': 'Influence',
    'Vratar': 'Goalkeeper',
    'Branilec': 'Defender',
    'Vezist': 'Midfielder',
    'Napadalec': 'Forward'
}

SLO_LABELS = {v: k for k, v in ENG_LABEL.items()}

def login(username, password):
    login_url = 'https://www.dugout-online.com/home/none/Free-online-football-manager-game'
    data = {
        'attemptLogin': 1,
        'do_user': username,
        'do_pass': password
    }

    session = requests.Session()
    response = session.post(login_url, data=data)
    time.sleep(0.1)
    return session

def get_player_age(player_tag):
    td = player_tag.getparent().getparent().getparent().getparent()
    age_td = td.getnext()
    age_span = age_td.find("span[@class='tableText']")
    return age_span.text

def add_team_ages(root, players):
    player_tags = root.xpath(".//a[contains(@href, 'playerID')]")
    player_ages = {}
    for tag in player_tags:
        player_id = tag.get('href').split('/')[-3]
        player_age = get_player_age(tag)
        player_ages[player_id] = int(player_age)

    for player in players:
        player['age'] = player_ages[player['id']]
        
    return players

def group_to_players(group):
    players = []
    player_tags = group.findall('option')
    for player in player_tags:
        player_id = player.get('value')
        player_name = player.text
        players.append({'id': player_id, 'name': player_name})

    return players

def get_players(session):
    first_players_url = '{}/players/none/clubid/0/Free-online-football-manager-game'.format(DO_URL)
    youth_players_url = '{}/players/none/view/youth/clubid/0'.format(DO_URL)
    
    first_response = session.get(first_players_url)
    time.sleep(0.1)
    youth_response = session.get(youth_players_url)
    time.sleep(0.1)

    parser = etree.HTMLParser()
    first_root = etree.fromstring(first_response.text, parser=parser)
    youth_root = etree.fromstring(youth_response.text, parser=parser)

    groups = first_root.findall('.//optgroup')[:2]
    first_team_group = groups[0]
    youth_team_group = groups[1]

    first_team_players = group_to_players(first_team_group)
    youth_team_players = group_to_players(youth_team_group)
    
    first_team_players = add_team_ages(first_root, first_team_players)
    youth_team_players = add_team_ages(youth_root, youth_team_players)
    return first_team_players, youth_team_players

def parse_training_chart_script(script_text):
    datasets_key_index = script_text.find('datasets:')
    if datasets_key_index == -1:
        return [], []

    array_start = script_text.find('[', datasets_key_index)
    if array_start == -1:
        return [], []

    depth = 0
    in_string = False
    string_quote = ''
    escape_next = False
    array_end = -1
    for idx in range(array_start, len(script_text)):
        ch = script_text[idx]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == '\\':
                escape_next = True
            elif ch == string_quote:
                in_string = False
        else:
            if ch == '"' or ch == "'":
                in_string = True
                string_quote = ch
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    array_end = idx
                    break
    if array_end == -1:
        return [], []

    array_literal = script_text[array_start:array_end + 1]

    def quote_keys(s: str) -> str:
        return re.sub(r'([\{\s,])(\w+)\s*:', r'\1"\2":', s)

    json_like = quote_keys(array_literal)
    json_like = re.sub(r"'", '"', json_like)
    json_like = re.sub(r',\s*([\]\}])', r'\1', json_like)

    try:
        datasets = json.loads(json_like)
    except json.JSONDecodeError:
        cleaned = re.sub(r',\s*([\]\}])', r'\1', json_like)
        datasets = json.loads(cleaned)

    labels_key_index = script_text.find('labels:')
    labels = []
    if labels_key_index != -1:
        labels_start = script_text.find('[', labels_key_index)
        if labels_start != -1:
            depth = 0
            in_string = False
            string_quote = ''
            escape_next = False
            labels_end = -1
            for idx in range(labels_start, len(script_text)):
                ch = script_text[idx]
                if in_string:
                    if escape_next:
                        escape_next = False
                    elif ch == '\\':
                        escape_next = True
                    elif ch == string_quote:
                        in_string = False
                else:
                    if ch == '"' or ch == "'":
                        in_string = True
                        string_quote = ch
                    elif ch == '[':
                        depth += 1
                    elif ch == ']':
                        depth -= 1
                        if depth == 0:
                            labels_end = idx
                            break
            if labels_end != -1:
                labels_literal = script_text[labels_start:labels_end + 1]
                labels_json = re.sub(r"'", '"', labels_literal)
                labels_json = re.sub(r',\s*([\]\}])', r'\1', labels_json)
                try:
                    labels = json.loads(labels_json)
                except json.JSONDecodeError:
                    labels = []

    if labels:
        labels = [label if label.endswith('.') else f"{label}." for label in labels]

    return datasets, labels

def add_date_labels(datasets, date_labels):
    for skill_data in datasets:
        for i in range(len(skill_data['data'])):
            skill_data['data'][i] = {'date': date_labels[i], 'value': skill_data['data'][i]}
    return datasets

def get_training_chart(root):
    charts_div = root.xpath(".//div[@id='charts']")
    if not charts_div:
        return []
    charts_div = charts_div[0]
    script_tags = charts_div.xpath('.//script')
    if not script_tags:
        return []

    script_text = ''.join([tag.text or '' for tag in script_tags])
    if not script_text:
        return []

    datasets, date_labels = parse_training_chart_script(script_text)
    datasets = add_date_labels(datasets, date_labels)
    datasets, player_cap = process_training_chart(datasets)
    return datasets, player_cap

def translate_label(dataset):
    try:
        dataset['label_en'] = ENG_LABEL[dataset['label']]
    except KeyError:
        dataset['label_en'] = dataset['label']
        dataset['label'] = SLO_LABELS[dataset['label']]
    return dataset

def process_training_cap(datasets):
    min_cap = 50
    for skill_data in datasets:
        capped = False
        cap = -1
        
        for i in range(len(skill_data['data']) - 1):
            if skill_data['data'][i + 1]['value'] < skill_data['data'][i]['value']:
                if not capped:
                    capped = True
                    cap = int(skill_data['data'][i]['value'])
                    break
        
        skill_data['capped'] = capped
        skill_data['cap'] = cap

        if (cap < min_cap) and (cap != -1):
            min_cap = cap
    
    return datasets, min_cap

def process_training_pops(datasets, player_cap):
    for skill_data in datasets:
        pops = 0
        drops = 0
        for i in range(len(skill_data['data']) - 1):
            if (skill_data['data'][i + 1]['value'] < skill_data['data'][i]['value'] and
                int(skill_data['data'][i]['value']) != 50):
                drops += 1

            if int(skill_data['data'][i + 1]['value']) > int(skill_data['data'][i]['value']):
                if (int(skill_data['data'][i + 1]['value']) > player_cap):
                    pops += 1

        skill_data['pops'] = pops
        skill_data['drops'] = drops
    
    return datasets

def process_training_chart(datasets):
    for dataset in datasets:
        dataset = translate_label(dataset)
        del dataset['borderColor']
        del dataset['borderWidth']
        del dataset['backgroundColor']
        del dataset['pointRadius']
        del dataset['pointHoverRadius']
        del dataset['pointBorderWidth']
        del dataset['pointBorderColor']
        del dataset['pointBackgroundColor']
        del dataset['fill']

    datasets = [data for data in datasets if data['label_en'] not in POSITION_ATTR]
    datasets = [data for data in datasets if data['hidden'] == False]

    datasets, player_cap = process_training_cap(datasets)
    datasets = process_training_pops(datasets, player_cap)

    return datasets, player_cap

def get_training_data(session, player_id, club_id):
    player_url = f'https://www.dugout-online.com/players/details/youth/0/playerID/{player_id}/club_id/{club_id}'
    response = session.get(player_url)
    time.sleep(0.1)
    parser = etree.HTMLParser()
    player_root = etree.fromstring(response.text, parser=parser)
    training_chart, player_cap = get_training_chart(player_root)
    return training_chart, player_cap

def parse_label_date(label):
    try:
        day = int(label[0:2])
        month = int(label[3:5])
        return (month, day)
    except Exception:
        return (0, 0)

def calculate_player_level_data(training_chart):
    min_cap = 50
    player_pops = 0
    player_drops = 0

    for sd in training_chart:
        player_pops += sd.get('pops', 0)
        player_drops += sd.get('drops', 0)
        if (sd.get('cap', -1) != -1) and (sd['cap'] < min_cap):
            min_cap = sd['cap']

    if (player_pops + player_drops) > 0:
        player_pops_ratio = player_pops / (player_pops + player_drops)
    else:
        player_pops_ratio = -1

    return min_cap, player_pops, player_drops, player_pops_ratio

def merge_training_charts(player, output_dir):
    player_name = player['name'].split(' ')[1]
    player_path = os.path.join(output_dir, f"{player_name}_{player['id']}.json")
    if os.path.exists(player_path):
        with open(player_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    else:
        existing = None

    if existing:
        label_to_existing = {d.get('label_en', d.get('label')): d for d in existing.get('training_chart', [])}
        merged_chart = []
        for current_ds in player['training_chart']:
            key = current_ds.get('label_en', current_ds.get('label'))
            existing_ds = label_to_existing.get(key)
            if not existing_ds:
                merged_ds = current_ds
            else:
                existing_dates = set(p['date'] for p in existing_ds.get('data', []))
                new_points = [p for p in current_ds.get('data', []) if p['date'] not in existing_dates]
                if new_points:
                    existing_ds['data'].extend(new_points)
                    existing_ds['data'].sort(key=lambda p: parse_label_date(p['date']))
                existing_ds['hidden'] = current_ds.get('hidden', existing_ds.get('hidden'))
                existing_ds['label'] = current_ds.get('label', existing_ds.get('label'))
                existing_ds['label_en'] = current_ds.get('label_en', existing_ds.get('label_en'))
                merged_ds = existing_ds
            merged_chart.append(merged_ds)
        current_keys = set(d.get('label_en', d.get('label')) for d in player['training_chart'])
        for k, ds in label_to_existing.items():
            if k not in current_keys:
                merged_chart.append(ds)

        merged_chart, merged_player_cap = process_training_cap(merged_chart)
        merged_chart = process_training_pops(merged_chart, merged_player_cap)

        existing['id'] = player['id']
        existing['name'] = player['name']
        existing['age'] = player['age']
        existing['training_chart'] = merged_chart

        player_cap, player_pops, player_drops, player_pops_ratio = calculate_player_level_data(merged_chart)
        #existing['player_cap'] = player_cap
        existing['player_pops'] = player_pops
        existing['player_drops'] = player_drops
        existing['player_pops_ratio'] = player_pops_ratio

        out_obj = existing
    else:
        player_cap, player_pops, player_drops, player_pops_ratio = calculate_player_level_data(player['training_chart'])
        player['player_cap'] = player_cap
        player['player_pops'] = player_pops
        player['player_drops'] = player_drops
        player['player_pops_ratio'] = player_pops_ratio

        out_obj = player

    return out_obj, player_path

def write_player_data(player_path, out_obj):
    if out_obj.get('player_pops_ratio', -1) != -1:
        with open(player_path, 'w', encoding='utf-8') as f:
            json.dump(out_obj, f, ensure_ascii=False, indent=2)
        logging.debug('Wrote player data to %s', player_path)
        logging.info('%s \tPOPS: %s \tDROPS: %s \tRATIO: %s', out_obj['name'], out_obj['player_pops'], out_obj['player_drops'], out_obj['player_pops_ratio'])

def main():
    parser = argparse.ArgumentParser(description='Fetch and analyze Dugout Online training chart datasets for players.')
    parser.add_argument('-u', '--username', required=True, help='Dugout Online username')
    parser.add_argument('-p', '--password', required=True, help='Dugout Online password')
    parser.add_argument('-c', '--club-id', type=int, default=0, dest='club_id', help='Club ID (default: 0)')
    parser.add_argument('--max-age', type=int, default=30, dest='max_age', help='Maximum player age to include (default: 30)')
    parser.add_argument('-v', '--verbose', action='count', default=2, help='Increase verbosity (-v INFO, -vv DEBUG)')
    parser.add_argument('--log-file', default='training_data.log', help='Path to log file (default: training_data.log)')
    parser.add_argument('--output-dir', default='player_data', help='Path to output directory (default: player_data)')
    args = parser.parse_args()

    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(filename=args.log_file, level=log_level, format='%(asctime)s %(levelname)s: %(message)s', filemode='a')

    logging.info('start')
    session = login(args.username, args.password)
    first_team, youth_team = get_players(session)
    players = first_team + youth_team
    players = [player for player in players if player['age'] <= args.max_age]
    logging.info('fetched players data (count=%d)', len(players))

    for player in players:
        logging.debug('Fetching training data for %s (id=%s)', player['name'], player['id'])
        training_chart, player_cap = get_training_data(session, player['id'], args.club_id)
        player['training_chart'] = training_chart
        player['player_cap'] = player_cap
        
    logging.info('fetched training data')
 
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    total_pops = 0
    total_drops = 0
    for player in players:
        out_obj, player_path = merge_training_charts(player, output_dir)
        write_player_data(player_path, out_obj)
        total_pops += out_obj['player_pops']
        total_drops += out_obj['player_drops']

    print(f'Total POPS: {total_pops}')
    print(f'Total DROPS: {total_drops}')
    print(f'Ratio: {total_pops / (total_pops + total_drops)}')
        

if __name__ == '__main__':
    main()

