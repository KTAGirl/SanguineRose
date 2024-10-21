# wj2git
A set of scripts to enable github-centered collaboration on Wabbajack modlists

## This project is WIP! - NOT ready to be used yet. Below are PLANNED features

## Philosophy
wj2git is a companion to Wabbajack, enabling github-centered collaboration around a Wabbajack project. In plain English - **now several people can work on a Wabbajack project.** And that's without risks of overwriting each other work, with change tracking, and so on - in short, using all the bells and whistles provided by git and github ❗😀

## Prerequisites
### Accounts
**Steam** - to get Skyrim
**[NexusMods](https://www.nexusmods.com/)** (preferably premium) - for Wabbajack.

### Installed
*Steam*
*Skyrim*
*Wabbajack* from [wabbajack.org](https://www.wabbajack.org/).

*MO2* ([MO2 on Nexus](https://www.nexusmods.com/skyrimspecialedition/mods/6194?tab=files)) - bread and butter of any serious modding, hard requirement for Wabbajack.   

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
    + 3.7.3.0 # or something, it is a Wabbajack install folder
    + COLLABWJ # folder where Wabbajack builds *your* new and shiny version of the WJ image 
    + COLLABWJ-TEST # folder where you will install *your* version of WJ image to test it. It is a stripped-down copy of \Modding\MO2, and another portable instance of MO2
      + *no 'downloads' here*
      + mods # stripped down
      + profiles
      + overwrite
      + ...
    + GitHub
      + COLLABWJ # as it comes from GitHub, just scripts and .json config files 
      + wj2git
    + MO2 # portable instance of MO2, the one installed by Wabbajack
      + downloads # Your main downloads folder. You may have it in a different place, but for f..k's sake, keep it on SSD or NVMe
      + mods # your MO2 mods, HUGE folder
      + profiles
      + overwrite
      + ...
    + wabbajack.exe

## Workflow using github
We assume that the Wabbajack github project is already setup to use wj2git. Let's name it COLLABWJ. One example of such a project is [KTA](https://github.com/KTAGirl/KTA). Now, to collaborate, you need to:
- install Wabbajack image using the link from the COLLABWJ project.
  + all the usual Wabbajack stuff (pristine Skyrim folder, etc.) has to be followed
  + strictly speaking, information in github is sufficient to reconstruct the folders without Wabbajack, but this is a LOT of headache.
  + in a properly setup COLLABWJ project, you'll get an MO2 installation, with most of the tools (Bodyslide, FNIS, etc. etc.) already installed as a part of it.
  + as a part of this process, you will setup Downloads folder - and Wabbajack will fill its databases.
- you modify this installed MO2 (using MO2 etc.), making that small change you want to contribute
  + in a collaborative environment, changes should be as small as possible, and merged as quickly as possible. Otherwise, lots of the benefits of github will be lost. Not to mention that if you sit in your repo without merging for a while - merging will run into conflicts, and resolving them will become a nightmare.
- clone github repo of the COLLABWJ project, AND this very project.
- config your folders
   + by default, it is customarily configured that you have C:\Modding\, with WJ project installed within as C:\Modding\<COLLABWJ>, with C:\Modding\Github\wj2git, and C:\Modding\Github\<COLLABWJ> folders. In theory, it should work with other setups too (as long as no Windows-specific folders are involved), if not - please report an issue. 
- run `COLLABWJ.py -wj2git` from within the repo
   + it will update your C:\Modding\Github\<COLLABWJ> to reflect your changes. This is where the magic happens.
   + even though it is written in single-threaded Python - it usually finishes within a few minutes. 
- now, you have your modified C:\Modding\Github\<COLLABWJ>. From here, you can see the differences, and commit directly to the project (if you have permissions), or submit a pull request.
   + to merge:
      + EVERY TIME you pull into \Modding\Github\COLLABWJ, you MUST run `COLLABWJ.py -git2wj` (it is DIFFERENT from the one above 🤯). It will try to update your \Modding\COLLABWJ project with the new changes from the Github.
      + if a new COLLABWJ Wabbajack was released while you were working, you may need to install this new Wabbajack file. Make sure to install it to a SEPARATE folder - like C:\\Modding\COLLABWJ2\ ❗, while using THE SAME Downloads folder. wj2git doesn't use this install as such - but while making it, WJ will download new files, and update its databases - and these ARE used by wj2git.
      * After doing it - continue your merge efforts. As long as your changes don't modify the same files in COLLABWJ as the changes coming from Github - you're fine. In case of conflicts over the same files - for text files, usual Github merge logic applies, for binary ones (such as esps) wj2git tries to keep changes as separate as possible, so it MAY be possible to merge anyway. However, with binary files, there is always a risk that the conflict will be not easily resolvable. Actually, it may happen in any kind of Github development, and not only with binary files. Fortunately, IRL it happens quite rarely. 
   + ([Github Desktop](https://desktop.github.com/download/) is HIGHLY recommended here, but if you're a fan of command-line git, it will also do).
- you're done with your change. 
- to pull new version - in addition to usual pulling github, and similar to the merge described above, you need to:
   + pull new version of \Modding\Github\COLLABWJ
   + if available, install new Wabbajack to \Modding\COLLABWJ2
   + run `COLLABWJ.py -git2wj`

I know it is quite complicated, especially for ppl coming from traditionally non-collaborative modding scene, but the benefits of collaborative development of modlists, where one person can deal with NPCs, another with environment, another with ENB, another with scripting, and so on - are truly enormous. 
