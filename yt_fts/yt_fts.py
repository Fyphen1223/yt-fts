import click, tempfile, requests, datetime, csv

from yt_fts.search_utils import *
from yt_fts.db_utils import *
from yt_fts.download_utils import *
from yt_fts.utils import *
from yt_fts.update_utils import update_channel
from yt_fts.list_utils import list_channels

# semantic search
from yt_fts.semantic_serch.open_ai_auth import get_api_key, test_api_access
from yt_fts.semantic_serch.embeddings import get_openai_embeddings
                                                

YT_FTS_VERSION = "0.1.15"

@click.group()
@click.version_option(YT_FTS_VERSION, message='yt_fts version: %(version)s')
def cli():
    make_db()


@click.command(help="Lists channels saved in the database")
@click.option("--channel", default=None, help="Optional name or id of the channel to list")
def list(channel):
    if channel is None:
        list_channels()
    else:       
        channel_id = get_channel_id_from_input(channel)
        list_channels(channel_id)


@click.command( 
    help="""
    Download subtitles from a specified YouTube channel.

    You must provide the URL of the channel as an argument. The script will automatically extract the channel id from the URL.
    """
)
@click.argument("channel_url", required=True)
@click.option("--channel-id", default=None, help="Optional channel id to override the one from the url")
@click.option("--language", default="en", help="Language of the subtitles to download")
@click.option("--number-of-jobs", type=int, default=1, help="Optional number of jobs to parallelize the run")
def download(channel_url, channel_id, language, number_of_jobs):

    s = requests.session()
    handle_reject_consent_cookie(channel_url, s)

    if channel_id is None:
        channel_id = get_channel_id(channel_url, s)
    
    exists = check_if_channel_exists(channel_id)
    if exists:
        print("Error: Channel already exists in database")
        print("Use update command to update the channel")
        list_channels(channel_id)
        exit()

    channel_name = get_channel_name(channel_id, s)

    if channel_id:
        download_channel(channel_id, channel_name, language, number_of_jobs, s)
    else:
        print("Error finding channel id try --channel-id option")


@click.command( 
    help="""
    Updates a specified YouTube channel.

    You must provide the ID of the channel as an argument.
    Keep in mind some might not have subtitles enabled. This command
    will still attempt to download subtitles as subtitles are sometimes added later.
    """
)
@click.option("--channel", default=None, required=True, help="The name or id of the channel to update.")
@click.option("--language", default="en", help="Language of the subtitles to download")
@click.option("--number-of-jobs", type=int, default=1, help="Optional number of jobs to parallelize the run")
def update(channel, language, number_of_jobs):

    channel_id = get_channel_id_from_input(channel)
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos" 

    s = requests.session()
    handle_reject_consent_cookie(channel_url, s)

    channel_name = get_channel_name(channel_id, s)

    update_channel(channel_id, channel_name, language, number_of_jobs, s)


@click.command(
        help="""
        Search for a specified text within a channel, a specific video, or across all channels.
        """
)
@click.argument("search_text", required=True)
@click.option("--channel", default=None, help="The name or id of the channel to search in. This is required unless the --all or --video options are used.")
@click.option("--video", default=None, help="The id of the video to search in. This is used instead of the channel option.")
@click.option("--all", is_flag=True, help="Search in all channels.")
def search(search_text, channel, video, all):

    if len(search_text) > 40:
        show_message("search_too_long")
        exit()

    if all:
        print('Searching in all channels')
        get_text("all", search_text)
    elif video:
        print(f"Searching in video {video}")
        get_text_by_video_id(video, search_text)
    elif channel:
        channel_id = get_channel_id_from_input(channel)
        channel_name = get_channel_name_from_id(channel_id)
        channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
        print(f"Searching in channel \"{channel_name}\": {channel_url}")
        get_text(channel_id, search_text)
    else:
        print("Error: Either --channel, --video, or --all option must be provided")
        exit()


@click.command( 
    help="""
    Export search results from a specified YouTube channel or from all channels to a CSV file.

    The results of the search will be exported to a CSV file. The file will be named with the format "{channel_id or 'all'}_{TIME_STAMP}.csv" 
    """
)
@click.argument("search_text", required=True)
@click.option("--all", is_flag=True, help="Export from all channels")
@click.argument('channel', required=False)
def export(channel, search_text, all):
    if len(search_text) > 40:
        show_message("search_too_long")
        exit() 

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if all:
        file_name = f"all_{timestamp}.csv"
        click.echo(f"Exporting search results from all channels to csv: {file_name}")
        export_search("all", search_text, file_name)
    else:
        channel_id = get_channel_id_from_input(channel)
        file_name = f"{channel_id}_{timestamp}.csv"
        click.echo(f"Exporting search results to csv: {file_name}")
        export_search(channel_id, search_text, file_name)


@click.command( 
    help="""
    Delete a channel and all its data. 

    You must provide the name or the id of the channel you want to delete as an argument. 

    The command will ask for confirmation before performing the deletion. 
    """
)
@click.argument("channel", required=True)
def delete(channel):

    channel_id = get_channel_id_from_input(channel)
    channel_name = get_channel_name_from_id(channel_id) 
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

    print(f"Deleting channel {channel_name}: {channel_url}")
    print("Are you sure you want to delete this channel and all its data?")
    confirm = input("y/n: ")

    if confirm == "y":
        delete_channel(channel_id)
        print(f"Deleted channel {channel_name}: {channel_url}")
    else:
        print("Exiting")


@click.command( 
    help="""
    Generate embeddings for a channel or all channels.

    Requires an OpenAI API key to be set as an environment variable OPENAI_API_KEY.
    """
)
@click.option("--channel", default=None, help="The name or id of the channel to generate embeddings for. This is required unless the --all option is used.")
@click.option("--all", is_flag=True, help="Generate embeddings for all channels")
@click.option("--open-api-key", default=None, help="OpenAI API key. If not provided, the script will attempt to read it from the OPENAI_API_KEY environment variable.")
def generate_embedings(channel, all, open_api_key):

    if open_api_key:
        api_key = open_api_key
    else:
        api_key = get_api_key()

    if api_key is None:
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Run export OPENAI_API_KEY=<your_key> to set the key")
        exit()
    
    channel_id = get_channel_id_from_input(channel)
    channel_subs = get_all_subs_by_channel_id(channel_id)
    make_embeddings_db()
    get_openai_embeddings(channel_subs, api_key)

commands = [list, download, update, search, export, delete, generate_embedings]

for command in commands:
    cli.add_command(command)


def download_channel(channel_id, channel_name, language, number_of_jobs, s):
    """
    Downloads all the videos from a channel to a tmp directory
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
        list_of_videos_urls = get_videos_list(channel_url)
        download_vtts(number_of_jobs, list_of_videos_urls, language, tmp_dir)
        add_channel_info(channel_id, channel_name, channel_url)
        vtt_to_db(channel_id, tmp_dir, s)


def export_search(channel_id, text, file_name):
    """
    Calls search functions and exports the results to a csv file
    """
    if channel_id == "all":
        res = search_all(text)
    else:
        res = search_channel(channel_id, text)

    if len(res) == 0:
        show_message("no_matches_found")
        exit()

    with open(file_name, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Channel Name','Video Title', 'Quote', 'Time Stamp', 'Link'])
        
        for quote in res:
            video_id = quote["video_id"]
            channel_name = get_channel_name_from_video_id(video_id)
            video_title = get_title_from_db(video_id)
            time_stamp = quote["timestamp"]
            subs = quote["text"]
            time = time_to_secs(time_stamp) 

            writer.writerow([channel_name,video_title, subs.strip(), time_stamp, f"https://youtu.be/{video_id}?t={time}"])


def get_channel_id_from_input(channel_input):
    """
    Checks if the input is a rowid or a channel name and returns channel id
    """
    name_res = get_channel_id_from_name(channel_input) 
    id_res = get_channel_id_from_rowid(channel_input) 

    if id_res != None:
        return id_res
    elif name_res != None: 
        return name_res
    else:
        show_message("channel_not_found")
        exit()
    