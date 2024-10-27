# mo2git
A set of Python scripts to enable github-centered collaboration on MO2-based modlists. Designed to integrate with Wabbajack, but eventually should be able to work standalone (how fast is yet to see). 

## This project is WIP! - NOT ready to be used yet. Below are PLANNED features

## Philosophy
mo2git is a companion to MO2, allowing collaborating on MO2 modlists in GitHub. mo2git's idea is about the same as that of Wabbajack, but mo2git file is text-based, and much more granular. mo2git also embraces the idea of having tools installed within modlist, and running them on end-user box. Why downloading Bodyslide-generated meshes or DDSOot-optimized textures rather than running Bodyslide or DDSOpt locally (of course, it should be well-defined Bodyslide, coming with the install, but it will still be much smaller than all those meshes)? 

This, in turn, will enable teams working on different parts of the mod list. In plain English - **now several people can work on a MO2 project.** And that's without risks of overwriting each other work, with change tracking, and so on - in short, using all the bells and whistles provided by git and github ❗😀

Currently, mo2git is relying on Wabbajack's hashing, and image generation to be distributed. I am planning to keep this integration, but eventually mo2git should be able to work standalone. **This, in turn, will allow to distribute modlists with paid mods - something not allowed by WJ's license**. Most likely, however, mo2git's hashing and image generation are going to stay slower than that of WJ (currently it is MUCH slower), so integration with WJ is going to be important. 

### Similarities with Wabbajack
- Pristine Skyrim install. Even SKSE and ENB can be kept out of Skyrim folder, using Root Builder plugin to MO2.
- Building MO2 portabke instance from user's 'Downloads' folder. 

### Addditional features compared to Wabbajack

### Disadvantages compared to Wabbajack
- no UI. Any companion GitHub projects providing UI over mo2git's functionality are extremely welcome. I will happily support them (providing non-UI Python functions in mo2git) as long as the project is under permissive (and not copyleft) license.
- Slower operation when hashing and installing. It will become MUCH faster than it is now (I am planning to parallelize these), but competing with C# in Python is, well, difficult.

## Prerequisites
### Hardware
*whatever is necessary to run your modlist*

*16G RAM*, 32G strongly recommended

*additional size for your modlist, and some more* (we need to test install from the generated MO2 portable instance, don't we?)

### Accounts
*Steam* - to get Skyrim

*[NexusMods](https://www.nexusmods.com/)* (preferably premium) - for downloads.

### Installed
*Steam*

*Skyrim* (PRISTINE install folder is required for all WJ installs)

*Wabbajack* from [wabbajack.org](https://www.wabbajack.org/). *Make sure to go to WJ Settings and to login to Nexus!*. At some point, this will become optional. I am still going to keep integration with WJ (using their hash DB, and generating WJ image from mo2git's image). 

*You don't really need MO2, or most of the tools such as LOOT or xEdit - with a properly configured COLLABWJ project they will be installed into \Modding\MO2\ from Wabbajack image*

*MSVC* Can be downloaded from [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/). Make sure to check `Desktop Development with C++` checkbox. Necessary to install `py7zr` and `bethesda-structs` Python modules.

*Python v3.10+*. Can be downloaded from [Python Releases for Windows](https://www.python.org/downloads/windows/). Latest greatest will do. And no, there won't be a Python2 version. Make sure to put `py` into PATH too. And wj2git also needs the following modules:
- xxhash: use `py -m pip install xxhash` to install
- py7zr: use `py -m pip install py7zr` to install
- bethesda-structs: use `py -m pip install bethesda-structs` to install

### Recommended
*GitHub Desktop* [Download GitHub Desktop](https://desktop.github.com/download/)

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

## Workflow using github
We assume that the mo2git-based github project is already setup to use mo2git. Let's name it COLLAB. One example of such a project is [KTA](https://github.com/KTAGirl/KTA). Now, to collaborate, you need to:
- install Wabbajack image using the link from the COLLAB project, OR build it from COLLAB's GitHub directly.
  + all the usual Wabbajack stuff (pristine Skyrim folder, etc.) has to be followed
  + in a properly setup COLLAB project, you'll get an MO2 installation, with most of the tools (Bodyslide, FNIS, etc. etc.) already installed as a part of it.
  + as a part of this process, you will setup Downloads folder - and download your archives there (of course, you may use your existing Downloads folder, you do have one, don't you? :wink:)
- you modify this installed MO2 (using MO2 etc.), making that small change you want to contribute (everything goes in small changes, this is the way we're eating elefants)
  + in a collaborative environment, changes should be as small as possible, and merged as quickly as possible. Otherwise, lots of the benefits of github will be lost. Not to mention that if you sit in your repo without merging for a while - merging will run into conflicts, and resolving them will become a nightmare.
- clone github repo of the COLLAB project, and mo2git.
- config your folders
   + by default, it is customarily configured that you have C:\Modding\, with WJ project installed within as C:\Modding\<COLLAB-WJ>, with C:\Modding\Github\mo2git, and C:\Modding\Github\<COLLAB> folders. In theory, it should work with other setups too (as long as no Windows-specific folders are involved), if not - please report an issue. 
- run `COLLAB.py -mo2git` from within the repo
   + it will update your C:\Modding\Github\<COLLAB> to reflect your changes. This is where the magic happens.
   + even though it is written in single-threaded Python - it usually finishes within a few minutes. 
- now, you have your modified C:\Modding\Github\<COLLAB>. From here, you can see the differences, and commit directly to the project (if you have permissions), or submit a pull request.
   + to merge:
      + EVERY TIME you pull into \Modding\Github\COLLAB, you MUST run `COLLAB.py -git2mo` (it is DIFFERENT from the one above 🤯). It will try to update your \Modding\COLLAB project with the new changes from the Github.
      + if a new COLLAB Wabbajack was released while you were working, you may need to install this new Wabbajack file. Make sure to install it to a SEPARATE folder - like C:\\Modding\COLLAB-WJ2\ ❗, while using THE SAME Downloads folder. mo2git doesn't use this install as such - but while making it, WJ will download new files, and update its databases - and these ARE used by mo2git.
      * After doing it - continue your merge efforts. As long as your changes don't modify the same files in COLLAB as the changes coming from Github - you're fine. In case of conflicts over the same files - for text files, usual Github merge logic applies, for binary ones (such as esps) mo2git tries to keep changes as separate as possible, so it might be possible to merge anyway. However, with binary files, there is always a risk that the conflict will be not easily resolvable. Actually, it may happen in any kind of Github development, and not only with binary files. Fortunately, IRL it happens quite rarely. 
   + ([Github Desktop](https://desktop.github.com/download/) is HIGHLY recommended here, but if you're a fan of command-line git, it will also do).
- you're done with your change. 
- to pull new version - in addition to usual pulling github, and similar to the merge described above, you need to:
   + pull new version of \Modding\Github\COLLAB
   + if available, install new Wabbajack to \Modding\COLLAB-WJ2
   + run `COLLAB.py -git2mo`

I know it is quite complicated, especially for ppl coming from traditionally non-collaborative modding scene, but the benefits of collaborative development of modlists, where one person can deal with NPCs, another with environment, another with ENB, another with scripting, and so on - are truly enormous. 
