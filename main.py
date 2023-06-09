'''Download and parsing books'''
import argparse
import os
import time
import json

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pathvalidate import sanitize_filename

import url_processing
import parse_tululu_category as parse_genre


def parse_book_page(response):
    soup = BeautifulSoup(response.text, 'lxml')
    title_tag = soup.select_one("table.tabs h1")
    raw_title, raw_author = title_tag.text.split("::")
    title = raw_title.strip()
    author = raw_author.strip()
    image = soup.select_one('body div.bookimage img')['src']
    comments = soup.select('.texts .black')
    comments = [comment.text for comment in comments]
    genres_tags = soup.select("span.d_book a")
    genres = [tag.text for tag in genres_tags]
    return {
        'title': title,
        'author': author,
        'image': image,
        'comments': comments,
        'genres': genres,
    }


def download_book(
        base_url, book_id, books_dir,
        images_dir, comments_dir, root_dir,
        skip_img, skip_txt, json_path
):
    book_response = requests.get(f'{base_url}/txt.php', {'id': f'{book_id}'})
    book_response.raise_for_status()
    url_processing.check_for_redirect(book_response)
    response = requests.get(f'{base_url}/b{book_id}')
    response.raise_for_status()
    url_processing.check_for_redirect(response)
    book_description = parse_book_page(response)

    if not skip_img:
        image_url = f'{base_url}/{book_description["image"]}'
        if image_url.find('nopic.gif') > 0:
            return

        expansion = url_processing.get_file_type(image_url)
        if root_dir:
            images_dir = os.path.join(root_dir, images_dir)
        file_name = os.path.join(images_dir, f'book_{book_id}.{expansion}')
        url_processing.download_image(image_url, file_name)

    if not skip_txt:
        file_name = sanitize_filename(f'book_{book_id}')
        if root_dir:
            books_dir = os.path.join(root_dir, books_dir)
        file_name = f'{os.path.join(books_dir, file_name)}.txt'
        save_comments(comments_dir, book_description, root_dir, json_path, book_id)
        with open(file_name, 'w', encoding='utf-8') as file:
            file.write(book_response.text)


def save_comments(comments_dir, description, root_dir, json_path, book_id):
    if root_dir:
        file_name = root_dir
    elif json_path:
        file_name = json_path
    else:
        file_name = comments_dir

    file_name = os.path.join(file_name, 'descriptions.json')
    try:
        with open(file_name, "r",  encoding='utf-8') as file:
            file_data = file.read()
            comments = json.loads(file_data)
            comments[book_id] = description
    except FileNotFoundError:
        comments = {}
        comments[book_id] = description

    with open(file_name, 'w') as file:
        json.dump(comments, file, ensure_ascii=False, indent=4)
        return


def main():
    load_dotenv()
    books_dir = os.getenv('BOOKS_DIR', default='books')
    os.makedirs(books_dir, exist_ok=True)
    images_dir = os.getenv('IMAGES_DIR', default='images')
    os.makedirs(images_dir, exist_ok=True)
    comments_dir = os.getenv('DESCRIPTION_DIR', default='descriptions')
    os.makedirs(comments_dir, exist_ok=True)

    parser = argparse.ArgumentParser(description='Script download books')
    parser.add_argument('-s', '--start_page', help='first page id (default: 1)', type=int, default=1)
    parser.add_argument('-e', '--end_page', help='last page id (default: 0)', type=int, default=0)
    parser.add_argument('--skip_img', action='store_true', help='Turn off images download')
    parser.add_argument('--skip_txt', action='store_true', help='Turn off texts download')
    parser.add_argument('--root_dir', default='', help='Destination folder path', type=str)
    parser.add_argument('--json_path', default='', help='JSON folder path', type=str)
    args = parser.parse_args()

    end_id = args.end_page
    base_url = 'https://tululu.org'
    genre_id = 55
    start_page = args.start_page

    if not end_id:
        try:
            genre_page_url = f'{base_url}/l{genre_id}/'
            soup = parse_genre.get_soup(genre_page_url)
            end_id = int(soup.select_one('body table p.center').contents[-1].text)
        except requests.exceptions.HTTPError:
            print('<h1>The last page number not found</h1>')
            return
        except requests.exceptions.ConnectionError:
            print('No internet connection')
            return

    if args.start_page >= end_id:
        print(f'number of the start page {args.start_page} more than end page {end_id}')
        return

    books_dir = os.path.join(books_dir, f'genre_{genre_id}')
    images_dir = os.path.join(images_dir, f'genre_{genre_id}')
    comments_dir = os.path.join(comments_dir, f'genre_{genre_id}')
    os.makedirs(books_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(comments_dir, exist_ok=True)

    for page in range(start_page, end_id + 1, 1):
        genre_page_url = f"{base_url}/l{genre_id}/{page}/"
        try:
            soup = parse_genre.get_soup(genre_page_url)
        except requests.exceptions.HTTPError or requests.exceptions.ConnectionError:
            time.sleep(10)
            continue
        for book_url in parse_genre.get_books_urls(soup):
            book_number = ''.join(filter(lambda x: x.isdigit(), book_url))
            try:
                download_book(
                    base_url, book_number, books_dir,
                    images_dir, comments_dir, args.root_dir,
                    args.skip_img, args.skip_txt, args.json_path
                              )
            except requests.exceptions.HTTPError or requests.exceptions.ConnectionError:
                print(f'internet error for url {base_url}{book_url}')
                time.sleep(10)
                continue


if __name__ == '__main__':
    main()
