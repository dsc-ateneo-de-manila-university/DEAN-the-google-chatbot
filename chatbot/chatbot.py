from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request
from googlesearch import search
import concurrent.futures
import functools
import json
import lxml
import os
from chatbot.pymessenger_updated import Bot
import re
import requests
from threading import Thread
from time import sleep
import time

load_dotenv()

app = Flask(__name__)
ACCESS_TOKEN = os.environ['PAGE_ACCESS_TOKEN']
VERIFY_TOKEN = os.environ['VERIFY_TOKEN']
bot = Bot(ACCESS_TOKEN)
headers = {"User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"}
df = {}
    
number_of_results = 5 #Number of searches to send
count = 80 #Word count per message

def timeout(seconds_before_timeout):
    """
    Timeout decorator
    """
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            res = [Exception('function [%s] timeout [%s seconds] exceeded!' % (func.__name__, seconds_before_timeout))]
            def newFunc():
                try:
                    res[0] = func(*args, **kwargs)
                except Exception as e:
                    res[0] = e
            t = Thread(target=newFunc)
            t.daemon = True
            try:
                t.start()
                t.join(seconds_before_timeout)
            except Exception as e:
                print('error starting thread')
                raise e
            ret = res[0]
            if isinstance(ret, BaseException):
                raise ret
            return ret
        return wrapper
    return deco

@timeout(15)
def get_request(url):
    """
    Gets the website and scrapes it using BeautifulSoup
    """
    try:
        page = requests.get(url, headers = headers,timeout=10)
        if page.status_code != 200:
        #Page not loaded, go to the next URL
            return
    except:
        print('Link timed out')
        return
    
    soup = BeautifulSoup(page.content,'lxml')
    return soup
    

def scraper(url:str):
    """
    Scrapes the Link for Text and Formats
    """
    
    global count
    global headers
    
    soup = ''

    #Timeout decorator somewhere here (start)
    try:
        soup = get_request(url)
    except:
        return
    
    #Timeout decorator somewhere here (end)
    
    try:
        title = soup.find_all('title')[0].text.strip() + "\n(Link: " + url + " )\n---\n"
    except:
        return
    
    processed = [i for i in [tag.text.strip() for tag in soup.find_all() if tag.name in ['p']] if i]

    temp = ''' '''.join(processed).replace("\n"," ").replace("\r"," ").split(''' ''')
    article = [''' '''.join(temp[word:word+count]) for word in range(0,len(temp),count)]
    
    if len(article) < 4:
        #Page not loaded, go to the next URL
        return

    my_dict = {'title':title + ''' ''' + article[0][0:450],'article':article}

    return my_dict

def links(keyword:str):
    
    """
    Retrieves the links from the search results.
    """
    results = []
    links = search(keyword, num=10, stop=10, pause=2)
    
    #If the search yielded no results
    if not links:
        #The chatbot tells the person to refine their search
        return
    
    for item in links:
        results.append(item)
    
    return results
    
def push(results:list):
    
    """
    Multithreaded scraping 
    """

    global number_of_results

    threads = min(32,len(results))
    new_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        map_object = executor.map(scraper,results)
    for article in map_object:
        if article:
            new_list.append(article)
            if len(new_list) == number_of_results:
                return new_list
    return new_list

#We will receive messages that Facebook sends our bot at this endpoint 
@app.route("/", methods=['GET', 'POST'])

#stores variables
def receive_message():

    #remember list of articles and what are article the user is reading
    global df
    global output
    global message
    global string
    global articles
    global recipient_id
    global choice

    if request.method == 'GET':
        """Before allowing people to message your bot, Facebook has implemented a verify token
        that confirms all requests that your bot receives came from Facebook.""" 
        token_sent = request.args.get("hub.verify_token")

        return verify_fb_token(token_sent)
    #if the request was not get, it must be POST and we can just proceed with sending a message back to user
    else:
        # get whatever message a user sent the bot
        output = request.get_json()
        print(output)
        # for event in output['entry']:
        #added to remove for loops
        message = output['entry'][0]['messaging'][0]
            # for message in messaging:
        #unindented twice
        #Facebook Messenger ID for user so we know where to send response back to
        recipient_id = str(message['sender']['id'])

        #If user sent a message
        if message.get('message'):
            if message['message'].get('text'):
                string = message['message'].get('text').lstrip().split(' ',1)
                
                #If the person wants to search something
                if string[0].lower() == 'search' and len(string) >= 2:
                    articles = push(links(string[1]))
                    if articles:
                        articles.insert(0,1)
                        df[recipient_id] = articles
                #If the person mistakenly just said search
                    return "Messaged Processed"
                return "Messaged Processed"
            #MIGHT BE IN THE WRONG PLACE!
            #if user sends us a GIF, photo,video, or any other non-text item
            if message['message'].get('attachments'):
                #FUTURE DEVELOPMENT THINGOS
                pass
                return "Messaged Processed"
        #If user clicked one of the postback buttons
        elif message.get('postback'):
            print('DF Keys Existing: ',df.keys())
            print(df)
            #If user wants to read a specific article
            #update df with new choice
            if df.get(recipient_id):
                #retrieve choice from postback
                choice = int(message['postback']['payload'])
                df[recipient_id][0] = choice
        else:
            #how does this get triggered
            pass
    return "Message Processed"

#sends message
def send_article():
    if request.method == 'POST':
        if message.get('message'):
            if message['message'].get('text'):
                if string[0].lower() == 'search' and len(string) >= 2:
                    send_message(recipient_id,"Thank you for your search! Let me see what I can find. :)")
                    if articles:
                        for i in range(1,len(articles)):
                            #Send a button allowing them to read more of the article
                            buttons = [
                                            {
                                                "type":"postback",
                                                "title":"Read",
                                                "payload": i
                                            }
                                        ]
                            #Send the title and summary of the article
                            button_message(recipient_id,articles[i]['title'][0:500],buttons)
                    else:
                        send_message(recipient_id,'''I couldn't find anything on that, could you try making your search more specific? It would help if you asked a question! (Ex. "Who is the President of the Philippines?)''')
        elif message.get('postback'):
            if df.get(recipient_id):
                if message['postback']['title'] == 'Read':
                    #dictionary for buttons
                    buttons = [
                                    {
                                        "type":"postback",
                                        "title":"Read more",
                                        "payload":choice
                                    }
                                ]
                    #send button message
                    if len(df[recipient_id][choice]['article']) == 1:
                        send_message(recipient_id,df[recipient_id][choice]['article'][0])
                        df[recipient_id][choice]['article'] = "End"
                        send_message(recipient_id,"End of Article")
                    elif df[recipient_id][choice]['article'] == "End":
                        send_message(recipient_id,"End of Article")
                    else:
                        button_message(recipient_id,df[recipient_id][choice]['article'][0],buttons)
                        df[recipient_id][choice]['article'] = df[recipient_id][choice]['article'][1:]
                elif message['postback']['title'] == 'Read more':
                    buttons = [
                                    {
                                        "type":"postback",
                                        "title":"Read more",
                                        "payload":choice
                                    }
                                ]
                    print('Read More Keys: ',df.keys())
                    if len(df[recipient_id][choice]['article']) == 1:
                        send_message(recipient_id, df[recipient_id][choice]['article'][0])
                        df[recipient_id][choice]['article'] = "End"
                        send_message(recipient_id, "End of Article")
                    elif df[recipient_id][choice]['article'] == "End":
                        send_message(recipient_id, "End of Article")
                    else:
                        button_message(recipient_id, df[recipient_id][choice]['article'][0], buttons)
                        df[recipient_id][choice]['article'] = df[recipient_id][choice]['article'][1:]
            #If user clicks the get started button
            elif message['postback']['title'] == 'Get Started':
                send_message(recipient_id, "Hey, I'm Dean! I allow Filipinos to access Google Search at no cost. This app runs purely on Free Facebook Data.\n\nIf you want to get started, just ask me a question! Make sure you write 'search' before your query. I'm excited to learn with you!\n\nI hope that you continue to stay safe! :)")
            else:
                send_message(recipient_id, "Hi there! Could you please repeat your search? Make sure you write 'search' before your query. Ex. search Who is the President of the Philippines")


def verify_fb_token(token_sent):
    #take token sent by facebook and verify it matches the verify token you sent
    #if they match, allow the request, else return an error 
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return 'Invalid verification token'

#uses PyMessenger to send response to user
def send_message(recipient_id, response):
    #sends user the text message provided via input response parameter
    bot.send_text_message(recipient_id, response)
    return "success"    

#uses PyMessenger to send message with button to user
def button_message(recipient_id,response,buttons):
    #sends user the button message provided via input response parameter
    bot.send_button_message(recipient_id,response,buttons)
    return "success"

def timer(func):
    '''Print the Runtime of the decorated function'''
    @functools.wraps(func)
    def wrapper_timer(*args,**kwargs):
        start_time = time.perf_counter()
        value = func(*args,**kwargs)
        end_time = time.perf_counter()
        run_time = end_time - start_time
        print(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value
    return wrapper_timer

if __name__ == "__main__":
    app.run()