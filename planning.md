- Improve the structure
    - [x] Non-logged in user: 
        - [x] Home page with "Missour.ai" on the left and Login on the top right
        - [x] Missour.ai Home Page contains really brief description of what the application does: "Provides AI-based tools..."
    - [x] Logged in user: See all the sections
- Overall Improvements
    - [x] CSS styling from Code Academy project
    - [] Button styling
- Individual Section Updates
    - [x] Navigation pane
        - [x] Missouri statehouse background image
        - [x] Fixed to the top
        - [x] Display depends upon user being logged in/out
        - [x] Layout is Horizontal vs. Vertical
    - [] Home Page: Just add some basic content decsribing the application.  "Utilized AI to develop an understanding of Missouri politics"
    - [] Transcripts
        - [] Make the table a little cleaner
    - [] Transcripts/Specific Transcript
        - [x] Have the title "stick" to the top when scrolling down
        - [] Put the "Back to Transcripts" link at the top
    - [x] Upload Audio: No Change
- Screen Size Adjustments
    - [] Navigation Menu at top uses hamburger menu
        - [] Logic: Logged in and screen size is small
        - Process:
            - 1. Add in the hamburger menu HTML
            ```
            <input type="checkbox" id="menu-toggle" />
            <label for="menu-toggle" class="hamburger">&#9776;</label>
            ```
            - 2. Update rules to display/not display hamburger menu/list items based on the size of the screen
                - Logic considerations: only display hamburger if the user is logged on