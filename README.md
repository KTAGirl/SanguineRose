# Sanguine Rose

**Sanguine Rose** is a tool that helps people work together to add hundreds of mods to a game.  It uses GitHub to share things, and makes managing big mod setups easier. *Sanguine Rose* is all about "modpacks" – groups of mods that make modding easier. You can use it for simple setups (just putting mods in the game folder) or for virtualized setups with mod managers like [Mod Organizer 2](https://www.modorganizer.org/) (MO2).

## This project is a Work In Progress! It’s not ready to use yet. Stay tuned! 

## WTF is modpack?

We all know about "mods" and "mod lists." But here's the problem: mods are too small to deal with one by one (managing 500 mods is a big hassle), and mod lists are too big and messy to work with easily (plus, most are "closed," meaning you can't really change them without breaking things).

Now, imagine if someone made a bunch of mods – like different looks for characters (3BA or BHUNP for females, SOS or SAM for males), weather mods+ENBs, FNIS+Nemesis, or whatever else – that were *super easy to reuse*. So, when you're setting up your own heavily modded game, you don't have to start from scratch – you can just *build on what others have already shared*, combine it as you wish, and simply add your own tweaks on top. It’s way easier to just say, "I want to use 3BA, this ENB+weather, and Nemesis, plus these few mods I’m really into," than setting up the whole thing from scratch.

That's where the idea of modpacks comes in. A modpack is a group of closely related mods that are not tightly tied to other mods. It can be as small as one mod or as big as a whole setup, but usually, it's somewhere in between. The key is that modpacks should be open – meaning you can add stuff without breaking everything. The best part is, you can mix and match modpacks, stacking them so each one adds something cool and useful.

Think of a modpack like a library in programming. It’s a building block for bigger projects. Just like in coding, modpacks should be ["highly cohesive"](https://en.wikipedia.org/wiki/Cohesion_(computer_science)#High_cohesion) (everything in the pack works well together) and ["loosely coupled"](https://en.wikipedia.org/wiki/Coupling_(computer_programming)) (they don’t break other mods or modpacks when you add them).

## On Sanguine Rose

**Sanguine Rose** is a tool for modders that makes it easy to work together on modpacks using GitHub. It's inspired by [Wabbajack](https://github.com/wabbajack-tools/wabbajack), but it's a totally separate project with a bunch of improvements (more on that below).

### An automated 'how to build' instruction 

Basically, each project made with *Sanguine Rose* is just a set of instructions (which are both computer-readable and human-readable) on how to build your game folder (and MO2 folder, if needed) from your Downloads folder. It’s like, "go to this URL, grab a file, unpack it, and copy file X from the archive to this spot." Rinse and repeat 200'000 times.

Oh, and with *Sanguine Rose* (unlike Wabbajack), you can easily see these instructions on GitHub. The build.json (which is actually a [JSON5](https://json5.org/) file) holds these instructions, so everything’s totally transparent. Plus, since it’s just text, you can use regular GitHub goodies like history tracking, merges, and pull requests to manage it.

### Using Sanguine Rose instead of Wabbajack

*Sanguine Rose* can be used to describe modpacks of any size, even entire modded setups. In that way, it could replace Wabbajack. But, I still encourage modpack creators to build their *Sanguine Rose* projects in a modular way, reusing others' work, and keeping things "open" for future changes. Huge, closed-off setups aren't really what *Sanguine Rose* is meant for.

## A Word to Mod Authors

The *Sanguine Rose* project is just a 'how to build' instruction and doesn't include any third-party copyrighted materials. With a *Sanguine Rose* modpack (just like with a Wabbajack modlist), users **still need to download your mod from the site where you've posted it.**


### Why Sanguine Rose is Good for Mod Authors

- 📢 Overall, *Sanguine Rose* aims to improve your bottom line (whether it’s more endorsements or more bitcoins) by making it easier for regular users to set up complex modded games.  It also tries to keep honest users away from those shady folks who share massive half-terabyte archives with hundreds of mods without getting permission from the mod authors. Unlike those modlists, *Sanguine Rose* projects don’t include any third-party copyrighted content, so **users still need to download your mods from wherever you’ve posted them.**
- ❤️ *Sanguine Rose* will provide a button to endorse all the mods included, and will advertise mod author's links to their Patreon, Discord, etc. 
- 👓 *Sanguine Rose* projects are 100% transparent. A faithfully-built *Sanguine Rose* project should contain **absolutely no** third-party material (and if someone copies your mod without permission, you’ll see it on GitHub and can ask GitHub to remove it). This is a big improvement over the non-transparent Wabbajack images.
- 🔧 I totally get that supporting users who are using third-party modpacks won't work. But supporting *modpack developers* – who handle support for their users – can save you a ton of effort. After all, it’s way easier to support one modpack developer than 100 users, and modpack creators are usually more dedicated and knowledgeable than regular mod users.
- 🔓 Last but not least, *Sanguine Rose* treats all mod authors as first-class citizens, *no matter where they post their mods*. So, if your mod is on Loverslab, it’ll get the same treatment as mods from Nexus (as long as I can get permission from Ashal). This includes things like showing screenshots while installing, links to your Patreon/Discord, bulk endorsements, and more. For mod authors on LL, this is a big upgrade over Nexus-focused Wabbajack. And smaller mod sites are welcome to submit their own plugins to provide the same features.

## Sanguine Rose vs Wabbajack
### Similarities with Wabbajack
 
- The idea is to build your whole game setup using a downloadable "image" (a 'how to build' instruction) and files from your Downloads folder.

### Advantages over Wabbajack

- 📂 modpacks. A modpack is a *Sanguine Rose*-described collection of closely related mods that are only loosely connected to the rest of the modding universe. For example, a female appearance modpack (like 3BA) is a work of art on its own, but it doesn't mess with things like environment, male appearance, or quest mods. The goal over time is to have tons of different modpacks on GitHub, so you can pick and choose the ones you want to use as building blocks for your own modpack or setup. It’s all about division of labor, specialization, and encouraging collaboration. 
- ✔️ No strict requirement to use Mod Organizer. Sure, MO2 is a great tool, and I personally recommend it, but if you prefer another way to build your modpack, that’s totally fine. [This depends on the "differential snapshots" feature, which is a bit guesswork, but hey – why not?] We should also be able to automatically convert between MO and non-MO setups.
- 🚯 No strict requirement to use "pristine" game folder either. I still highly recommend it, but I get that it can be tough. 
- 🗽*Sanguine Rose* is independent and neutral. This is in contrast with Wabbajack, where top 2 contributors are from Nexus Mods. Among other things it means that while WJ does not allow paid mods, *Sanguine Rose* is completely neutral on the topic. As a truly free piece of software, *Sanguine Rose* doesn’t impose any restrictions on users, end of story.
- 📄 *Sanguine Rose* image is not a monolithic binary file. Instead, it’s a GitHub project with a JSON5 file at its core, where all the changes are visible and most of them are even understandable.
- 👫 Multiple ppl can now work on the same *Sanguine Rose* modpack.
- ♻️ *Sanguine Rose* lets you share and reuse info like "what’s inside this particular archive." For known archives, there’s no need to spend time and energy extracting and hashing them on each computer, so reusing saves your time and reduces the global CO<sub>2</sub> footprint.
- 🔨 Concept of transform: Why uploading-downloading all those Bodyslide files or DDSOpt-optimized textures, when they can be generated on the end-user box (using exactly the same tools as you use, as all the tools and their config are just files described by *Sanguine Rose* project)? 
- 🔩 Automated calculation and application of file patches
- 💰 *Sanguine Rose* doesn’t have an issue with paid mods. Modders deserve to get paid for their work, after all. Just remember, as a modder, it’s your responsibility to follow all other licenses (including Bethesda’s).
- 📆 GitHub features like change tracking, merges, and pull requests are all available. And it’s up to you to decide whether to accept a pull request or not.
- 🚀 Better Performance: Sanguine Rose is highly parallelized and includes some major improvements over WJ logic. In fact, Sanguine Rose is already faster than Wabbajack, even though it uses Python allegedly slow Python rather than C#. `<troll mode>` Python rulezzzz! 🥇 `</troll mode>`
- [FUTURE] an alternative way (using ReFS's CoW feature) to provide MO2-like virtual file system but without MO2 running and hooking into the game processes. It might be a bit cleaner during runtime than MO2, though it could result in longer startup and shutdown times. It will still maintain MO2 compatibility and make MO-like development even cleaner than MO itself 🤣, as *Sanguine Rose* should be able to ensure that 100% of the changes go to the "overwrites" folder, keeping both the game and mod folders pristine (well, after *Sanguine Rose* restores them back 😉).

### Downsides Compared to Wabbajack

- ❌ No User Interface (UI): sanguine-rose project is already complicated enough, and I’m not really into UIs myself. That said, **if you want to create a GitHub project with a UI for Sanguine Rose, that would be awesome!** I’m happy to support such projects by providing non-UI functions in sanguine-rose, as long as your project uses a permissive license—no copyleft or other restrictions, please. This also means no stuff such as "Any quid-pro-quo payment structure in connection with... is strictly prohibited." either :angry: :rage: :scream:.

## Prerequisites

Note that the list below is for Skyrim. While sanguine-rose as such is game-neutral, supporting a game (in *sanguine-rose* speak, it is named "game universe") needs a "root" GitHub project - describing what "pristine" setup is, what are the well-known mods, where to get them, and so on. For example, for Skyrim such a root project is [sanguine-skyrim-root](https://github.com/dwemer-anonymous/sanguine-skyrim-root) (it was created using Sanguine Rose itself, but it requires some initial effort and quite a bit of maintenance). 

### Hardware
- *Whatever you need to run your setup.*
- *16GB RAM is a must; 32GB is super recommended.*
- *You’ll also need additional disk space, and quite a bit of it.*

### Accounts
- *Steam* - You’ll need this for original Skyrim. 
- *[NexusMods](https://www.nexusmods.com/)* (preferably premium) - You’ll use this for downloads.
- Accounts for all the other mod sites you are going to use (such as [LoversLab](https://www.loverslab.com/))

### Installed Stuff
- *Steam*
- *Skyrim*
- *You don’t necessarily need to install MO2 or tools like LOOT or xEdit separately. If you set up your YOUR-MODPACK project right, those will get installed into your portable MO2 instance by Sanguine Rose.*
- *Python v3.10+*. Grab it from [Python Releases for Windows](https://www.python.org/downloads/windows/). The latest version is perfect, and no, I'm not going to support Python 2. Make sure to add `py` to your PATH environment variable.
- You’ll also need to run sanguine-install.py from sanguine-rose project. It will download and install several things we need. 

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
    + YOUR-MODPACK-TEST # folder where you will install *your* version of YOUR-MODPACK project to test it. It is a stripped-down copy of \Modding\MO2, and another portable instance of MO2
      + *no 'downloads' here*
      + mods # stripped down
      + profiles
      + overwrite
      + ...
    + ANOTHER-YOUR-MODPACK-TEST # why not? you can develop several modpacks in parallel
    + GitHub
      + YOUR-MODPACK # as it comes from GitHub, just scripts and .json config files
      + PARENT-MODPACK
      + ANOTHER-PARENT-MODPACK
      + ANOTHER-YOUR-MODPACK # [OPTIONAL] why not?
      + skyrim-universe # basic stuff describing 'universe' of your game; things such as "how should pristine folder look", known archives and where to get them, and so on. 
      + sanguine-rose # this GitHub project
    + MO2 # portable instance of MO2, the one installed by `YOUR-MODPACK.py -install`
      + downloads # Your main downloads folder. You may have it in a different place, but for f..k's sake, keep it on SSD or NVMe
      + mods # your MO2 mods, HUGE folder
      + profiles
      + overwrite
      + ...
    
## Workflow Using GitHub

So, let’s assume you’ve got your hands on a *Sanguine Rose*-based GitHub modpack. We’ll call it YOUR-MODPACK. An example of such a project is [KTA](https://github.com/KTAGirl/KTA). Here’s how to work with it:

1. Clone YOUR-MODPACK GitHub project. Run `YOUR-MODPACK.bat -install` from it. 
   - It may take a while, but in a well-set-up YOUR-MODPACK project, as a result of running `YOUR-MODPACK.bat -install`, you’ll get an MO2 installation with most tools (like Bodyslide, FNIS, etc.) already set up.
   - You’ll also set up your Downloads folder to download your archives (feel free to use your existing Downloads folder, I'm sure you’ve got one, right? 😜). Multiple Downloads folders are supported too. 
   
2. Modify your installed modpack in MO2 portable instance (using Mod Organizer and included tools) to make that small change you want to make (think small changes—it’s like eating an elephant one bite at a time).
   - If there are several people working on the same modpack, try keep changes small and merge them quickly. Otherwise, you’ll lose a lot of the GitHub benefits. And if you let your copy sit too long without merging, resolving merge conflicts can get messy.
   
3. Clone the GitHub repo for the YOUR-MODPACK project and Sanguine Rose.
4. Set up your folders:
   - By default, you’d set up C:\Modding\, with the *Sanguine Rose*-based project in C:\Modding\<YOUR-MODPACK>, and the GitHub stuff in C:\Modding\Github\sanguine-rose and C:\Modding\Github\<YOUR-MODPACK>. It should work with other setups too, but let me know if you hit any issues.
   
5. Run `YOUR-MODPACK.bat -mo2git` from inside the YOUR-MODPACK folder.
   - This is where the magic happens. It will update your C:\Modding\Github\<YOUR-MODPACK> to show your changes. 
   - Even though it’s written in single-threaded Python, it usually wraps up in just a few minutes.
   
6. Now you’ve got your modified C:\Modding\Github\YOUR-MODPACK. Now you can see the differences and commit directly to the project (if you’ve got permissions) or submit a pull request.
   - To merge:
     - Every time you pull into \Modding\Github\YOUR-MODPACK, you *have to* run `YOUR-MODPACK.bat -git2mo` (yep, that’s different from the one above 🤯). This updates your \Modding\YOUR-MODPACK project with new changes from GitHub.
     - After that, keep merging your changes. As long as your edits don’t mess with the same files as the new GitHub changes, you’re golden. If there are conflicts, the usual GitHub merge rules apply for text files, and Sanguine Rose tries to keep binary file changes separate, so sometimes it’ll still work out. Just know that conflicts can still happen, but it’s pretty rare IRL.
     - ([Github Desktop](https://desktop.github.com/download/) is super recommended, but if you love the command line, that works too!)
   
7. You’re all done with your change!
   
8. To pull the new version, you’ll need to:
   - Pull the new version of \Modding\Github\YOUR-MODPACK
   - Run `YOUR-MODPACK.bat -git2mo`

I know it sounds complicated, especially if you’re used to solo modding, but the perks of working together on modpacks, like one person handling NPCs, another tweaking the environment, and someone else working on ENB or scripting—are huge!
