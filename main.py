import requests
import datetime
from PIL import Image, ImageDraw, ImageFont
import textwrap
import io
import os # Import os to access environment variables
import tempfile
import atexit
import shutil
import time
import tweepy

# --- Configuration ---
# Your OpenWeatherMap API key (Free Tier compatible)
# Get API key from environment variable
OPENWEATHER_API_KEY = os.getenv("YOUR_WEATHER_API_KEY")
# Ensure the key is not None and provide a fallback or error if not set
if not OPENWEATHER_API_KEY:
    print("Error: YOUR_WEATHER_API_KEY environment variable not set.")
    exit(1) # Exit if the key is missing

# List of major US cities for which to fetch weather data
CITIES = ["Chicago", "Phoenix", "Miami", "Orlando", "New York City"]
# Output path for the generated image
OUTPUT_IMAGE_PATH = "weather_forecast.png"

# --- Twitter API Configuration ---
# Get Twitter API credentials from environment variables
CONSUMER_KEY = os.getenv("YOUR_TWITTER_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("YOUR_TWITTER_CONSUMER_SECRET")
ACCESS_TOKEN = os.getenv("YOUR_TWITTER_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("YOUR_TWITTER_ACCESS_TOKEN_SECRET")

# Ensure all Twitter credentials are set
if not all([CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    print("Error: One or more Twitter API environment variables are not set.")
    exit(1) # Exit if any key is missing


# --- Color Palette (RGB tuples) ---
COLOR_DARK_BLUE = (33, 52, 72)      # #213448
COLOR_MEDIUM_BLUE = (84, 119, 146)  # #547792
COLOR_LIGHT_BLUE = (148, 180, 193) # #94B4C1 (not used in this version but available)
COLOR_LIGHT_YELLOW = (236, 239, 202) # #ECEFCA

# --- Temporary file cleanup (kept for general robustness, not specific to fonts anymore) ---
_temp_paths_to_cleanup = []

def cleanup_temp_paths():
    """Removes temporary files and directories created during execution."""
    for p_path in _temp_paths_to_cleanup:
        if os.path.exists(p_path):
            try:
                if os.path.isfile(p_path):
                    os.remove(p_path)
                elif os.path.isdir(p_path):
                    shutil.rmtree(p_path) # Use shutil.rmtree for directories
                # print(f"Cleaned up temporary path: {p_path}")
            except OSError as e:
                print(f"Error cleaning up temporary path {p_path}: {e}")

# Register the cleanup function to run on script exit
atexit.register(cleanup_temp_paths)


# --- Helper Functions for Weather Data Fetching ---

def get_current_weather(city, api_key):
    """
    Fetches current weather data for a given city from OpenWeatherMap.
    Uses the Free Tier 'weather' endpoint.
    Args:
        city (str): The name of the city.
        api_key (str): Your OpenWeatherMap API key.
    Returns:
        dict: A dictionary containing current weather information, or None if an error occurs.
    """
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key, # Use the passed api_key here
        "units": "imperial" # Use imperial units for Fahrenheit and miles/hour
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Raise an exception for HTTP errors (e.g., 404, 500)
        data = response.json()

        # Validate essential keys and data structure
        if (data.get("main") and
            data.get("weather") and isinstance(data["weather"], list) and len(data["weather"]) > 0 and
            data.get("wind")):
            return {
                "temperature": data["main"].get("temp"),
                "feels_like": data["main"].get("feels_like"),
                "description": data["weather"][0].get("description"),
                "wind_speed": data["wind"].get("speed"),
                "wind_deg": data["wind"].get("deg"),
                "humidity": data["main"].get("humidity"),
                "main_weather": data["weather"][0].get("main")
            }
        else:
            print(f"Incomplete or malformed current weather data for {city}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching current weather for {city}: {e}")
        return None
    except Exception as e: # Catch any other unexpected errors during parsing
        print(f"Unexpected error parsing current weather data for {city}: {e} - Raw data: {data}")
        return None

def get_forecast(city, api_key):
    """
    Fetches 3-hour forecast data for a given city from OpenWeatherMap.
    This function retrieves the first available 3-hour forecast entry, which is the most immediate.
    Uses the Free Tier 'forecast' endpoint.
    Args:
        city (str): The name of the city.
        api_key (str): Your OpenWeatherMap API key.
    Returns:
        dict: A dictionary containing the next 3-hour forecast information, or None if an error occurs.
    """
    base_url = "http://api.openweathermap.org/data/2.5/forecast"
    params = {
        "q": city,
        "appid": api_key, # Use the passed api_key here
        "units": "imperial" # Use imperial units for Fahrenheit and miles/hour
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        # Validate essential keys and data structure
        if (data.get("list") and isinstance(data["list"], list) and len(data["list"]) > 0 and
            data["list"][0].get("main") and
            data["list"][0].get("weather") and isinstance(data["list"][0]["weather"], list) and len(data["list"][0]["weather"]) > 0 and
            data["list"][0].get("wind")):
            first_forecast_entry = data["list"][0]
            return {
                "dt_txt": first_forecast_entry.get("dt_txt"),
                "temperature": first_forecast_entry["main"].get("temp"),
                "description": first_forecast_entry["weather"][0].get("description"),
                "pop": first_forecast_entry.get("pop"),
                "wind_speed": first_forecast_entry["wind"].get("speed"),
                "main_weather": first_forecast_entry["weather"][0].get("main")
            }
        else:
            print(f"Incomplete or malformed forecast data for {city}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching forecast for {city}: {e}")
        return None
    except Exception as e: # Catch any other unexpected errors during parsing
        print(f"Unexpected error parsing forecast data for {city}: {e} - Raw data: {data}")
        return None

def get_wind_direction(deg):
    """
    Converts wind degrees to a cardinal direction (e.g., 0-22.5 -> N, etc.).
    Args:
        deg (float): Wind direction in degrees.
    Returns:
        str: Cardinal wind direction.
    """
    directions = [
        "North", "North-Northeast", "Northeast", "East-Northeast", "East", "East-Southeast",
        "Southeast", "South-Southeast", "South", "South-Southwest", "Southwest", "West-Southwest",
        "West", "West-Northwest", "Northwest", "North-Northwest"
    ]
    # Normalize degrees to be within 0-360
    deg = deg % 360
    # Calculate index into directions array
    idx = round(deg / (360. / len(directions))) % len(directions)
    return directions[idx]

# --- Text Formatting Function ---

def format_weather_text(city, data):
    """
    Formats the fetched weather data into a human-readable paragraph.
    Args:
        city (str): The name of the city.
        data (dict): A dictionary containing 'current' and 'forecast' weather data.
    Returns:
        str: Formatted weather information for the city.
    """
    current = data.get("current")
    forecast = data.get("forecast")

    if not current:
        return f"**{city}**\n\nWeather data not available for {city}.\n\n"

    current_temp = round(current["temperature"])
    feels_like_temp = round(current["feels_like"])
    description = current["description"].lower()
    wind_speed = round(current["wind_speed"])
    wind_direction = get_wind_direction(current["wind_deg"])
    humidity = current["humidity"]

    current_text = (
        f"{city} is currently experiencing {description} conditions with a temperature of {current_temp}°F. "
        f"It feels like {feels_like_temp}°F due to {humidity}% humidity. "
        f"Winds are light, blowing from the {wind_direction} at {wind_speed} mph. "
    )

    forecast_text = ""
    if forecast:
        pop_percent = round(forecast["pop"] * 100)
        forecast_description = forecast["description"].lower()
        forecast_temp = round(forecast["temperature"])

        outlook = "expect mostly clear skies"
        if pop_percent > 70:
            outlook = "prepare for heavy precipitation"
        elif pop_percent > 30:
            outlook = "anticipate scattered showers"
        elif pop_percent > 0:
            outlook = "see a slight chance of light rain"

        forecast_text = (
            f"Over the next three hours, {city} will {outlook} with temperatures around {forecast_temp}°F. "
            f"The probability of precipitation is {pop_percent}%. "
            f"Conditions are expected to remain {forecast_description}."
        )
    else:
        forecast_text = "Forecast data for the next three hours is not available."

    return f"**{city}**\n\n{current_text}\n\n{forecast_text}\n\n"

# --- Image Generation Logic ---

def generate_weather_image(weather_texts):
    """
    Generates a PNG image with the formatted weather text.
    The image height is dynamically calculated based on the content.
    Args:
        weather_texts (list): A list of formatted weather text strings for each city.
    Returns:
        bytes: The image data in PNG format.
    """
    # Image dimensions and padding
    width = 1200
    padding_x = 50
    padding_y = 30
    line_spacing = 5 # Reduced line spacing for tighter text within paragraphs
    paragraph_spacing = 18 # Space between current weather and forecast paragraphs
    city_block_spacing = 10 # Space between different city weather blocks (reduced from previous, adjusted for template)
    footer_height = 30 # Estimated height for the footer text
    footer_padding_y = 30 # Increased padding above the footer

    # --- Font Loading ---
    def load_system_font(font_name, size):
        """
        Attempts to load a system font (Arial, Arial Rounded MT) or falls back to PIL default.
        """
        font_paths = {
            "Arial Rounded MT Bold": [
                "/Library/Fonts/Arial Rounded Bold.ttf", # macOS
                "/usr/share/fonts/truetype/msttcorefonts/ARLRDBD.TTF", # Linux (common name)
                "C:/Windows/Fonts/ARLRDBD.TTF", # Windows (common name)
                "ARLRDBD.TTF", # Current directory fallback
                "/Library/Fonts/Arial Rounded MT Bold.ttf", # macOS common
            ],
            "Arial Rounded MT Regular": [
                "/Library/Fonts/Arial Rounded.ttf", # macOS
                "/usr/share/fonts/truetype/msttcorefonts/ARLRDR.TTF", # Linux (common name)
                "C:/Windows/Fonts/ARLRDR.TTF", # Windows (common name)
                "ARLRDR.TTF", # Current directory fallback
                "/Library/Fonts/Arial Rounded MT Regular.ttf", # macOS common
            ],
            "Arial-Bold": [
                "/Library/Fonts/Arial Bold.ttf", # macOS
                "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf", # Linux
                "C:/Windows/Fonts/arialbd.ttf", # Windows
                "arialbd.ttf" # Current directory fallback
            ],
            "Arial-Regular": [
                "/Library/Fonts/Arial.ttf", # macOS
                "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf", # Linux
                "C:/Windows/Fonts/arial.ttf", # Windows
                "arial.ttf" # Current directory fallback
            ]
        }
        
        for path in font_paths.get(font_name, []):
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except IOError:
                    continue
        
        print(f"Could not find system font '{font_name}'. Using default PIL font.")
        return ImageFont.load_default().font_variant(size=size)

    # Use Arial Rounded MT for titles and city names
    title_font = load_system_font("Arial Rounded MT Bold", 36)
    city_title_font = load_system_font("Arial Rounded MT Bold", 31)
    # Use Arial Regular for body/description text and footer
    body_font = load_system_font("Arial-Regular", 22.5)
    footer_font = load_system_font("Arial-Bold", 22)

    # --- Calculate Required Image Height ---
    current_y = padding_y
    # Add height for the main title
    title_text = "Current Weather & 3-Hour Forecast: Major US Cities"
    # Create a dummy ImageDraw object for initial text size calculations
    dummy_img = Image.new('RGB', (1, 1))
    dummy_d = ImageDraw.Draw(dummy_img)

    title_bbox = dummy_d.textbbox((0,0), title_text, font=title_font)
    title_height = title_bbox[3] - title_bbox[1]
    current_y += title_height + padding_y # Space after title

    # Calculate effective wrapping width in pixels
    max_text_block_width_pixels = width - 2 * padding_x
    # Estimate average character width for body font for textwrap
    # Use a representative string for better average character width
    test_string_for_width = "the quick brown fox jumps over the lazy dog"
    avg_char_width_pixels = dummy_d.textlength(test_string_for_width, font=body_font) / len(test_string_for_width)
    # Calculate character count for textwrap, with a small buffer
    wrap_width_chars = int(max_text_block_width_pixels / avg_char_width_pixels * 0.95)
    # Ensure a reasonable minimum character width
    wrap_width_chars = max(wrap_width_chars, 50) 


    # Calculate height needed for each city's text block
    for text_block in weather_texts:
        lines = text_block.split('\n')
        for line in lines:
            if line.strip().startswith('**') and line.strip().endswith('**'):
                # City title line (e.g., **New York City**)
                city_name = line.strip().replace('**', '')
                bbox = dummy_d.textbbox((0,0), city_name, font=city_title_font)
                current_y += (bbox[3] - bbox[1]) + paragraph_spacing
            else:
                # Body text line - wrap dynamically based on calculated char width
                wrapped_lines = textwrap.wrap(line, width=wrap_width_chars)
                for wrapped_line in wrapped_lines:
                    bbox = dummy_d.textbbox((0,0), wrapped_line, font=body_font)
                    current_y += (bbox[3] - bbox[1]) + line_spacing
                if line.strip() == "": # Add extra space for empty lines (paragraph breaks)
                    current_y += paragraph_spacing

        current_y += city_block_spacing # Space between different city blocks

    # Add height for the footer
    current_y += footer_padding_y
    footer_text = "Weather data provided by OpenWeatherMap"
    footer_bbox = dummy_d.textbbox((0,0), footer_text, font=footer_font)
    current_y += (footer_bbox[3] - footer_bbox[1])

    final_height = current_y + padding_y # Add bottom padding to the total height

    # --- Create and Draw Image ---
    img = Image.new('RGB', (width, int(final_height)), color = COLOR_LIGHT_YELLOW) # Background color
    d = ImageDraw.Draw(img)

    # Draw the main title
    title_bbox = d.textbbox((0,0), title_text, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    d.text(((width - title_width) / 2, padding_y), title_text, fill=COLOR_DARK_BLUE, font=title_font)

    # Starting Y position for the first city's weather information
    y_offset = padding_y + title_height + padding_y

    # Draw each city's weather text
    for text_block in weather_texts:
        lines = text_block.split('\n')
        for line in lines:
            if line.strip().startswith('**') and line.strip().endswith('**'):
                # Draw city title
                city_name = line.strip().replace('**', '')
                d.text((padding_x, y_offset), city_name, fill=COLOR_DARK_BLUE, font=city_title_font)
                bbox = d.textbbox((0,0), city_name, font=city_title_font)
                y_offset += (bbox[3] - bbox[1]) + paragraph_spacing
            else:
                # Draw wrapped body text using the dynamically calculated character width
                wrapped_lines = textwrap.wrap(line, width=wrap_width_chars)
                for wrapped_line in wrapped_lines:
                    d.text((padding_x, y_offset), wrapped_line, fill=COLOR_DARK_BLUE, font=body_font)
                    bbox = d.textbbox((0,0), wrapped_line, font=body_font)
                    y_offset += (bbox[3] - bbox[1]) + line_spacing
                if line.strip() == "": # Add extra space for empty lines
                    y_offset += paragraph_spacing

        y_offset += city_block_spacing # Space after each city's block

    # Draw the footer
    footer_text = "Weather data provided by OpenWeatherMap"
    footer_bbox = d.textbbox((0,0), footer_text, font=footer_font)
    footer_width = footer_bbox[2] - footer_bbox[0]
    # Center the footer horizontally
    d.text(((width - footer_width) / 2, y_offset + footer_padding_y), footer_text, fill=COLOR_MEDIUM_BLUE, font=footer_font)


    # Save the image to a BytesIO object (in-memory)
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()

    return img_byte_arr

def upload_image_to_twitter(image_path, tweet_text):
    """
    Uploads an image to Twitter using API v1.1 for media and creating the tweet with API v2.
    This is required for the current Twitter API Free Tier.
    Args:
        image_path (str): The path to the image file to upload.
        tweet_text (str): The text content of the tweet.
    Returns:
        bool: True if the tweet was successful, False otherwise.
    """
    try:
        # --- Step 1: Authenticate and upload media using v1.1 API ---
        # This part is still necessary and allowed on the Free tier.
        auth = tweepy.OAuth1UserHandler(CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
        api = tweepy.API(auth)
        
        print(f"Uploading image '{image_path}' to Twitter media endpoint...")
        media = api.media_upload(filename=image_path)
        print("Image uploaded successfully. Media ID:", media.media_id)

        # --- Step 2: Create the tweet using the v2 API client ---
        # This is the new part to comply with the Free tier limits.
        client = tweepy.Client(
            consumer_key=CONSUMER_KEY,
            consumer_secret=CONSUMER_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET
        )

        print(f"Posting tweet using API V2: {tweet_text}")
        # The create_tweet method is the v2 equivalent of update_status
        client.create_tweet(text=tweet_text, media_ids=[media.media_id])
        
        print("Tweet posted successfully!")
        return True

    except tweepy.errors.TweepyException as e:
        print(f"Error uploading to Twitter: {e}")
        # Add more specific advice for the 403 error
        if '403 Forbidden' in str(e):
            print("A 403 error suggests a problem with your Twitter App's permissions.")
            print("Please ensure your app in the Twitter Developer Portal has 'Read and Write' permissions.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during Twitter upload: {e}")
        return False

def main():
    # Dictionary to store all fetched weather data
    all_city_weather_data = {}
    for city in CITIES:
        print(f"Fetching weather data for {city}...")
        current = get_current_weather(city, OPENWEATHER_API_KEY)
        forecast = get_forecast(city, OPENWEATHER_API_KEY)
        all_city_weather_data[city] = {"current": current, "forecast": forecast}

    # List to store formatted text for each city
    formatted_texts = []
    for city, data in all_city_weather_data.items():
        formatted_texts.append(format_weather_text(city, data))

    print("Generating image...")
    # Generate the image bytes
    image_bytes = generate_weather_image(formatted_texts)

    # Save the generated image bytes to a file
    with open(OUTPUT_IMAGE_PATH, "wb") as f:
        f.write(image_bytes)
    print(f"Weather forecast image generated and saved as '{OUTPUT_IMAGE_PATH}'")

    # --- Twitter Post Functionality ---
    print("Waiting for 1 second before uploading to Twitter...")
    time.sleep(1) # Wait for 1 second

    # Generate dynamic tweet text
    # The current time for the tweet will be based on the system's current time
    # but converted to UTC as requested in the tweet format.
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    # Get the current day of the week (e.g., "Thursday", "Friday")
    current_day_of_week = now_utc.strftime("%A") 

    # Format the time as "03 July, 5:55 PM UTC" (example)
    # The .replace(" 0", " ") is to remove leading zero from day if it exists (e.g., "03" -> " 3")
    dynamic_date_time_str = now_utc.strftime("%d %B, %I:%M %p UTC").replace(" 0", " ") 
    
    cities_for_tweet = ", ".join(CITIES[:-1]) + ", & " + CITIES[-1] # "Chicago, Phoenix, Miami, Orlando, & New York City"

    tweet_message = (
        f"Hello!👋 {current_day_of_week} weather update for {cities_for_tweet} as of {dynamic_date_time_str}. "
        f"Check the image for details!\n"
        f"#WeatherUpdate #USCities #Chicago #Phoenix #Miami #Orlando #NYC"
    )

    upload_image_to_twitter(OUTPUT_IMAGE_PATH, tweet_message)


if __name__ == "__main__":
    main()