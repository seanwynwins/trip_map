# Bookmarklet Method - No Browser Automation Needed!

This is the **easiest method** - it works with your normal browser session, no special setup required!

## Step 1: Create the Bookmarklet

1. Open the file `bookmarklet.js` in this directory
2. **Copy the entire JavaScript code** (it starts with `javascript:(function(){`)

3. In your browser (Brave/Chrome):
   - **Option A**: Right-click your bookmarks bar → "Add page"
   - **Option B**: Go to Bookmarks → Bookmark Manager → Add new bookmark
   - Name it: **"Extract TripAdvisor Places"**
   - In the URL field, **paste the entire JavaScript code** you copied
   - Save

## Step 2: Extract Your Places

1. **Open your normal Brave browser** (no special flags needed!)
2. **Log into TripAdvisor** (if not already)
3. **Navigate to**: https://www.tripadvisor.com/Trips
4. **Scroll down** to load all your trips (make sure all places are visible)
5. **Click the bookmarklet** you just created (in your bookmarks bar)
6. A **JSON file will automatically download** with all your place links!

## Step 3: Process the JSON File

In your terminal:

```bash
source .venv/bin/activate
python -m src.cli_ta_export_bookmarklet --input ~/Downloads/tripadvisor_places_*.json --output output/tripadvisor_places.csv
```

Replace `~/Downloads/tripadvisor_places_*.json` with the actual filename of the downloaded file.

This will:
- Read the JSON file with all place URLs
- Visit each place page to get location details
- Save everything to CSV

## Step 4: Generate Your Map

```bash
python -m src.generate_map --input output/tripadvisor_places.csv --output output/visited_map.html
```

## Advantages of This Method

✅ **Works with your normal browser** - no special launch needed  
✅ **No CAPTCHA issues** - you're using your regular browser session  
✅ **No remote debugging** - just click a bookmark  
✅ **Simple and reliable** - extracts data directly from the page

## Troubleshooting

**No places extracted?**
- Make sure you've scrolled to load all your trips
- Make sure you're on the trips page (not individual trip pages)
- Try scrolling more and clicking the bookmarklet again

**JSON file not downloading?**
- Check your browser's download settings
- Make sure pop-ups/downloads aren't blocked
- The file should be in your Downloads folder


