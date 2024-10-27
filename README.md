# mo2git

Hey there! **mo2git** is a bunch of Python scripts to help you collaborate on MO2 modlists using GitHub. It’s made to work with Wabbajack, but I’m hoping it’ll eventually run on its own (still figuring out the speed).

## Just a heads-up: This project is a Work In Progress! Not ready for action yet. Check out the features I'm planning below.

## Philosophy

**mo2git** is a companion to MO2, making it easy to team up on modlists using GitHub. Think of it like Wabbajack, but mo2git uses a text file format that's GitHub-friendly. Plus, it supports having the tools right in your modlist and running them on user's system. Why make user download all those BodySlide-generated meshes or DDSOot-optimized textures when you can just run BodySlide or DDSOpt locally on their box? (While it means you need Bodyslide included with the install, it’ll still save tons of space compared to downloading gigabytes of meshes!). And being smaller means being more GiuHub-friendly too!

In short, mo2git means that multiple people can work on different parts of the mod list without stepping on each other’s toes. You’ll get change tracking, pull requests, and all the other cool features that come with Git and GitHub! ❗😀

Right now, mo2git relies on Wabbajack’s hashing and install image generation. I’m planning to keep this integration, but eventually, I want mo2git to stand on its own. **That’ll let you share modlists with paid mods, which isn’t allowed with Wabbajack’s license.** Just a heads-up, though: mo2git’s hashing and image generation are slower than Wabbajack’s, so we’ll definitely keep the integration going for a while.

### Similarities with Wabbajack

- You absoulutely must have a pristine Skyrim install. You should even keep SKSE and ENB out of your Skyrim folder by using the Root Builder plugin for MO2.
- You build a portable MO2 setup from "image" and files from your Downloads folder.

### Extra Features Compared to Wabbajack
- image is not a monolithic binary. Instead, it is a text file, with all the changes visible and understandable.
- **multiple ppl can now work on the same modlist. Yahoo!**
- change tracking. It is clear what has changed since previous version, and it can be rolled back easily. 
- pull requests from ppl outside of your immediate team. And you decide whethe4r to accept them or not. 

### Downsides Compared to Wabbajack

- No UI. If you or someone else wants to whip up a companion GitHub project with a UI for mo2git, that’d be awesome! I’m all in for supporting that (providing non-UI Python functions in mo2git) as long as your project is under a permissive license.
- Slower performance when hashing and installing. I plan to speed things up by parallelizing some tasks, but, let’s be real, competing with C# in Python is tough.

## Prerequisites

### Hardware
- *Whatever you need to run your modlist.*
- *16GB RAM is a must; 32GB is super recommended.*
- *You’ll also need 2x of extra space for your modlist, plus some more.*

### Accounts
- *Steam* - You’ll need this for Skyrim.
- *[NexusMods](https://www.nexusmods.com/)* (preferably premium) - You’ll use this for downloads.

### Installed Stuff
- *Steam*
- *Skyrim* (Make sure it’s a PRISTINE install folder)
- *Wabbajack* from [wabbajack.org](https://www.wabbajack.org/). *Don’t forget to log in to Nexus in WJ Settings! Eventually, this will be optional, but I’m keeping the integration with WJ (using their hash DB and generating WJ images from mo2git's images).*
- *You don’t necessarily need MO2 or tools like LOOT or xEdit—if you set up a COLLABWJ project right, those will get installed into \Modding\MO2 from the Wabbajack image.*
- *MSVC* can be grabbed from [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/). Just check the `Desktop Development with C++` box. You’ll need this to install the `py7zr` and `bethesda-structs` Python modules.
- *Python v3.10+*. Grab it from [Python Releases for Windows](https://www.python.org/downloads/windows/). The latest version is perfect, and no, I'm not going to support Python 2. Make sure to add `py` to your PATH. You’ll also need these modules:
  - xxhash: Install with `py -m pip install xxhash`
  - py7zr: Install with `py -m pip install py7zr`
  - bethesda-structs: Install with `py -m pip install bethesda-structs`

### Recommended
- *GitHub Desktop* [Download GitHub Desktop](https://desktop.github.com/download/)

## Typical folder structure
+ C:\
  + Steam # it doesn't matter much where it is installed, as long as it is not in "special" Windows folders
    + steamapps
      + common
        + Skyrim Special Edition
          + Data
  + Modding
    + [OPTIONAL] 3.7.3.0 # or something, it is where Wabbajack itself (but not modlists) is installed
    + [OPTIONAL] COLLAB-WJ # folder where Wabbajack builds *your* new and shiny version of the WJ image
    + [OPTIONAL] COLLAB-WJ2 # folder where you install updated Wabbajack build.
    + COLLAB-TEST # folder where you will install *your* version of WJ image to test it. It is a stripped-down copy of \Modding\MO2, and another portable instance of MO2
      + *no 'downloads' here*
      + mods # stripped down
      + profiles
      + overwrite
      + ...
    + [OPTIONAL] ANOTHER-COLLAB-WJ # why not?
    + ANOTHER-COLLAB-TEST
    + GitHub
      + COLLAB # as it comes from GitHub, just scripts and .json config files
      + ANOTHER-COLLAB # why not?
      + mo2git
    + MO2 # portable instance of MO2, the one installed by Wabbajack
      + downloads # Your main downloads folder. You may have it in a different place, but for f..k's sake, keep it on SSD or NVMe
      + mods # your MO2 mods, HUGE folder
      + profiles
      + overwrite
      + ...
    + wabbajack.exe

## Workflow Using GitHub

So, let’s assume you’ve got your hands at a mo2git-based GitHub project. We’ll call it COLLAB. An example of this kind of project is [KTA](https://github.com/KTAGirl/KTA). Here’s how to work with it:

1. Install the Wabbajack image using the link from the COLLAB project or build it straight from COLLAB’s GitHub.
   - Make sure to follow all the usual Wabbajack steps (like having a pristine Skyrim folder).
   - In a well-set-up COLLAB project, you’ll get an MO2 installation with most tools (like Bodyslide, FNIS, etc.) already set up.
   - You’ll also set up your Downloads folder to download your archives (feel free to use your existing Downloads folder, I'm sure you’ve got one, right? 😜).
   
2. Modify your installed modlist in MO2 portable instance (using Mod Organizer and included tools) to make that small change you want to make (think small changes—it’s like eating an elephant one bite at a time).
   - In a collaborative setup, keep changes small and merge them quickly. Otherwise, you’ll lose a lot of the GitHub benefits. And if you let your copy sit too long without merging, resolving merge conflicts can get messy.
   
3. Clone the GitHub repo for the COLLAB project and mo2git.
4. Set up your folders:
   - By default, you’d set up C:\Modding\, with the WJ project in C:\Modding\<COLLAB-WJ>, and the GitHub stuff in C:\Modding\Github\mo2git and C:\Modding\Github\<COLLAB>. It should work with other setups too, but let me know if you hit any issues.
   
5. Run `COLLAB.py -mo2git` from inside the COLLAB folder.
   - This is where the magic happens. It will update your C:\Modding\Github\<COLLAB> to show your changes. 
   - Even though it’s written in single-threaded Python, it usually wraps up in just a few minutes.
   
6. Now you’ve got your modified C:\Modding\Github\COLLAB. Now you can see the differences and commit directly to the project (if you’ve got permissions) or submit a pull request.
   - To merge:
     - Every time you pull into \Modding\Github\COLLAB, you *have to* run `COLLAB.py -git2mo` (yep, that’s different from the one above 🤯). This updates your \Modding\COLLAB project with new changes from GitHub.
     - If a new COLLAB Wabbajack was released while you were working, you’ll need to install that new Wabbajack file to a SEPARATE folder—like C:\\Modding\COLLAB-WJ2\ ❗—but still use the same Downloads folder. mo2git doesn’t use this COLLAB-WJ2 install as is, but WJ will download new files and update its databases, which mo2git will use.
     - After that, keep merging your changes. As long as your edits don’t mess with the same files as the new GitHub changes, you’re golden. If there are conflicts, the usual GitHub merge rules apply for text files, and mo2git tries to keep binary file changes separate, so sometimes it’ll still work out. Just know that conflicts can still happen, but it’s pretty rare IRL.
     - ([Github Desktop](https://desktop.github.com/download/) is super recommended, but if you love the command line, that works too!)
   
7. You’re all done with your change!
   
8. To pull the new version, you’ll need to:
   - Pull the new version of \Modding\Github\COLLAB
   - If available, install the new Wabbajack to \Modding\COLLAB-WJ2
   - Run `COLLAB.py -git2mo`

I know it sounds complicated, especially if you’re used to solo modding, but the perks of working together on modlists, like one person handling NPCs, another tweaking the environment, and someone else working on ENB or scripting—are huge!
