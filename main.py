import sqlite3
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import smtplib

def get_listings():
    """
    Extracts URLs from Funda based on given parameters

    Returns:
        links ([str]): URLs 
    """
    try:
        # Retrieving scraper API key and setting up parameters for the HTML query
        # Scraper API is used to prevent from being identified as a bot
        api_key = os.getenv('scraper_api_key')
        url = os.getenv('funda_url')
        country_code = 'eu'
        device_type = 'desktop'
        url_scraper = 'https://api.scraperapi.com/'

        # Making a payload with our request variables
        payload = {
            'api_key': api_key,
            'url': url,
            'country_code': country_code,
            device_type: device_type
        }

        # Executing our HTML request, and parsing it
        response = requests.get(url_scraper, params=payload)
        soup = BeautifulSoup(response.content, 'html.parser')

        # We find all the divs with class flex justify-between
        # Then we loop through all those divs to find the a tag with the href
        # We add all the links to the links array
        links = []
        divs = soup.find_all('div', class_='flex justify-between')
        for div in divs:
            link = div.find('a').get('href')
            links.append(link)

        print()

        return links

    except Exception as e:
        print(f"An error occurred in get_listings: {e}")
        exit()

def connect_to_sql():
    """
    Establishes a connection to a SQLite3 database.
    It creates one if it doesn't exist yet.
    Also creates the staging and target tables if they don't exist yet.
    
    Returns:
        connection, cursor (tuple): connection, cursor
    """
    try:
        # Makes our connection
        conn = sqlite3.connect('.db')
        cursor = conn.cursor()

        # Makes target table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS LISTINGS (
                URL TEXT PRIMARY KEY,
                FLAG BOOLEAN NOT NULL,
                INSERT_TIMESTAMP TEXT NOT NULL,
                UPDATE_TIMESTAMP TEXT NOT NULL
            );
        ''')
        conn.commit()

        # Makes staging table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS LISTINGS_STAGING (
                URL TEXT
            );
        ''')
        conn.commit()

        print("Connection to database established")

        return conn, cursor
    
    except Exception as e:
        print(f"An error occurred in connect_to_sql: {e}")
        exit()

def insert_records_staging(conn, cursor, links):
    """
    Inserts records into the staging table

    Args:
        conn (sqlite3.Connection): connection
        cursor (sqlite3.Cursor): cursor
        links ([str]): links to be inserted
    """
    try:
        # Loop through links and insert each link into staging table
        for link in links:
            cursor.execute("INSERT INTO LISTINGS_STAGING (URL) VALUES (?);", [link])
        conn.commit()
        print('Records inserted into staging table')

    except Exception as e:
        print(f"An error occured in insert_records: {e}")
        exit()

def insert_records_target(conn, cursor):
    """
    Moves records from staging to target

    Args:
        conn (sqlite3.Connection): connection
        cursor (sqlite3.Cursor): cursor
    """
    try:
        # Merges records from staging to target
        cursor.execute('''
            INSERT INTO
                LISTINGS (
                    URL,
                    FLAG,
                    INSERT_TIMESTAMP,
                    UPDATE_TIMESTAMP
                )
            SELECT
                URL,
                FALSE AS FLAG,
                DATETIME() AS INSERT_TIMESTAMP,
                DATETIME() AS UPDATE_TIMESTAMP
            FROM
                LISTINGS_STAGING
            WHERE
                URL NOT IN (
                    SELECT
                        URL
                    FROM
                        LISTINGS
                );
        ''')
        conn.commit()
        print('Records moved from staging to target')

        # Empty staging table
        cursor.execute('''
            DELETE FROM
                LISTINGS_STAGING;
        ''')
        conn.commit()
        print('Records removed from staging table')

    except Exception as e:
        print(f"An error occurred in insert_records_target: {e}")
        exit()

def get_new_listings(conn, cursor):
    """
    Gets URLs that have not been flagged yet from the database

    Args:
        conn (sqlite3.Connection): connection
        cursor (sqlite3.Cursor): cursor

    Returns:
        new_listings ([str]): new listings
    """
    try:
        # Get listings that have not been flagged yet
        cursor.execute('''
            SELECT
                URL
            FROM
                LISTINGS
            WHERE
                FLAG = FALSE;
        ''')

        new_listings_tup = cursor.fetchall()

        # Fetchall returns array with tuples, convert to just an array
        new_listings = []
        for new_listing in new_listings_tup:
            new_listings.append(new_listing[0])

        print('Retrieved new listings')

        return new_listings

    except Exception as e:
        print(f"An error occurred in get_new_listings: {e}")
        exit()

def mail_new_listings(new_listings, conn, cursor):
    """
    Gets the unflagged listings from the database, e-mails them, then flags all unflagged records in the database

    Args:
        new_listings ([str]): new listings
        conn (sqlite3.Connection): connection
        cursor (sqlite3.Cursor): cursor
    """
    try:
        # E-mail content
        from_email = os.getenv('from_email_address')
        to_email = os.getenv('to_email_address')
        subject = "New Funda Listings"
        body = "\n\n".join(new_listings)

        # SMTP server configuration
        smtp_server = os.getenv('from_email_smtp')
        smtp_port = os.getenv('from_email_port')
        smtp_password = os.getenv('from_email_password')

        # Connect to SMTP server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(from_email, smtp_password)

        # Construct e-mail headers
        message = f"From: {from_email}\nTo: {to_email}\nSubject: {subject}\n\n{body}"

        # Send e-mail
        server.sendmail(from_email, to_email, message)
        server.quit()

        print("E-mail sent succesfully")

        # Flag unflagged records
        cursor.execute('''
            UPDATE
                LISTINGS
            SET
                FLAG = TRUE,
                UPDATE_TIMESTAMP = DATETIME()
            WHERE
                FLAG = FALSE;
        ''')
        conn.commit()

        print("Flagged all unflagged records")

    except Exception as e:
        print(f"An error occurred in mail_new_listings: {e}")
        exit()

def main():
    load_dotenv()

    links = get_listings()
    conn, cursor = connect_to_sql()
    insert_records_staging(conn, cursor, links)
    insert_records_target(conn, cursor)
    new_listings = get_new_listings(conn, cursor)
    
    # Only send an e-mail if there are new listings
    if len(new_listings) > 0:
        mail_new_listings(new_listings, conn, cursor)
    else:
        print("No new listings to send")

if __name__ == "__main__":
    main()