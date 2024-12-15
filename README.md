# Sanguine Rose

**Sanguine Rose** is a tool that helps people work together to add hundreds of mods to a game.  It uses GitHub to share things, and makes managing big mod setups easier. *Sanguine Rose* is all about "modpacks" – groups of mods that make modding easier. You can use it for simple setups (just putting mods in the game folder) or for virtualized setups with mod managers like [Mod Organizer 2](https://www.modorganizer.org/) (MO2).

## This project is a Work In Progress! It’s not ready to use yet. Stay tuned! 

## WTF is modpack?

We all know about "mods" and "mod lists." But here's the problem: mods are too small to deal with one by one (managing 500 mods is a big hassle), and mod lists are too big and messy to work with easily (plus, most are "closed," meaning you can't really change them without breaking things).

Now, imagine if someone made a bunch of mods – like different looks for characters (3BA or BHUNP for females, SOS or SAM for males), weather mods+ENBs, FNIS+Nemesis, or whatever else – that were *super easy to reuse*. So, when you're setting up your own heavily modded game, you don't have to start from scratch – you can just *build on what others have already shared*, combine it as you wish, and simply add your own tweaks on top. It’s way easier to just say, "I want to use 3BA, this ENB+weather, and Nemesis, plus these few mods I’m really into," than setting up the whole thing from scratch.

That's where the idea of modpacks comes in. A modpack is a group of closely related mods that are not tightly tied to other mods. It can be as small as one mod or as big as a whole setup, but usually, it's somewhere in between. The key is that modpacks should be open – meaning you can add stuff without breaking everything. The best part is, you can mix and match modpacks, stacking them so each one adds something cool and useful.

Think of a modpack like a library in programming. It’s a building block for bigger projects. Just like in coding, modpacks should be ["highly cohesive"](https://en.wikipedia.org/wiki/Cohesion_(computer_science)#High_cohesion) (everything in the pack works well together) and ["loosely coupled"](https://en.wikipedia.org/wiki/Coupling_(computer_programming)) (they don’t break other mods or modpacks when you add them).

## On Sanguine Rose

**Sanguine Rose** is a tool for modders that makes it easy to collaborate on modpack development using GitHub. *Sanguine Rose* is inspired by [Wabbajack](https://github.com/wabbajack-tools/wabbajack), but is a completely separate development, with lots of improvements (more on it below). 


### An automated 'how to build' instruction 

In essence, each Sanguine Rose-based project is just a (machine-executable, but human-readable) *instruction on 'how to build your game folder (and MO2 folder, if applicable) from Downloads folder'*. As in "go to such and such URL, get a file there, unpack it, and copy file X from the archive to this target". Rinse and repeat 200'000 times.

BTW, with Sanguine Rose (and unlike with WJ), you can easily see this instruction on GitHub. build.json (which is actually a [JSON5](https://json5.org/) file) is this instruction, so the whole thing is absolutely transparent. And as it is a text-based instruction - it can be managed by using standard GitHub mechanisms (history tracking, merges, pull requests, and so on). 

### Using in lieu of Wabbajack

*Sanguine Rose* can be used to describe arbitrarily large modpacks, to the extent of the whole modded setup. In this sense, it can be used as a replacement for Wabbajack. Still, I am encouraging modpack developers to build your *Sanguine Rose* projects in modular manner, reusing work of the others, and keeping things "open" for the downstream changes. While I cannot prohibit using *Sanguine Rose* in other manner, huge closed monolithic setups are certainly not what *Sanguine Rose* is designed for. 

## A Word to Mod Authors

*Sanguine Rose* project, being merely a *'how to build' instruction*, does not include any third-party copyrighted materials. With *Sanguine Rose* modpack (just like with Wabbajack modlist) users **still have to download your mod from the site where you have posted it**.

### Why Sanguine Rose is Beneficial for mod authors

- 📢 Overall, *Sanguine Rose* aims to improve your bottom line (whether measured in endorsements or in bitcoins) by enabling Joe Average user to make complicated setups, and by taking honest users away from those swindling folks who publish those whole downloadable half-terabyte folders without mod author's permission. **Unlike such modlists, *Sanguine Rose* projects do not include anything copyrighted, so end-users still need to download mods from wherever you decided to publish it**
- ❤️ *Sanguine Rose* will provide a button to endorse all the mods included, and will advertise mod author's links to Patreon, Discord, etc. 
- 👓 *Sanguine Rose* projects are 100% transparent. A faithfully-built *Sanguine Rose* project should contain **exactly zero** third-party material (and if your mod is copied without your permission - you'll be able to see it on GitHub, and ask GitHub to remove it). This is a major improvement over non-transparent Wabbajack images.
- 🔧 I realize perfectly well that supporting users who are using 3rd-party modpacks, is not an option. However, *supporting modpack writers - who take care of supporting their users themselves - will save you a lot of effort*. After all, supporting 1 modpack developer is easier than supporting 100 users, and also we can expect that modpack developers are more dedicated and more knowledgeable than mod users.
- 🔓 Last but not least, *Sanguine Rose* considers *all* mod authors as first-class citizens, *regardless of where they post their mods*. In other words, if your mod is on Loverslab (or anywhere else for that matter), it will get the same treatment as mods from Nexus (well, as long as I can get a permission from site owner). This will include screenshots while installing, links to your Patreon/Discord, bulk endorsements, and so on. For mod authors from LL, it is a major improvement over Nexus-centric Wabbajack. And smaller sites are very welcome to submit their own plugins to provide equivalent functionality. 

## Comparison with Wabbajack
### Similarities with Wabbajack
 
- The idea is to build the whole game setup from some downloadable "image" ('how to build' instruction), and files from your Downloads folder.

### Advantages over Wabbajack

- 📂 modpacks. Modpack is a *Sanguine Rose*-described bunch of closely related mods, which are only loosely related to the rest of the mod universe. For example, making a nice-looking female appearance modpack (such as 3BA) is a piece of art by itself, but it does not interfere too much with environment modding, or with male appearance modpack, or with quest mods. I hope that with time, there will be various modpacks all over github, so you can choose which ones to use as building blocks for your own modpack or setup. It is all about division of labor,   specialization, and encouraging collaboration.
- ✔️ No strict requirement to use Mod Organizer. Sure, MO2 is a beautiful tool, and I am using it myself and wholeheartedly recommend it, but if you prefer other ways to build your mod pack - it is up to you. [this depends on "differential snapshots" feature, which is inherently heuristical, but hey - why not?] We should also be able to convert between MO and non-MO setups automatically.
- 🚯 No strict requirement to use "pristine" game folder either. I still super recommend it, but I know how difficult it is. 
- 🗽*Sanguine Rose* is independent and neutral. This is in contrast with Wabbajack, where top 2 contributors are from Nexus Mods. Among other things it means that while WJ does not allow paid mods, Sanguine Rose is completely neutral about it; as a piece of truly free software, Sanguine Rose doesn't feel like imposing any restrictions on the users, period. 
- 📄 *Sanguine Rose* image is not a monolithic binary. Instead, it is a github project (with JSON5 file at its heart), with all the changes visible and most of them even understandable.
- 👫 multiple ppl can now work on the same *Sanguine Rose* modpack.
- ♻️ *Sanguine Rose* allows to share and re-use information such as "what's inside this particular archive", speeding things up (for such known archives, there is no need to extract and hash them locally on each box, saving time and global CO<sub>2</sub> footprint).  
- 🔨 concept of transform: why uploading-downloading all those Bodyslide files  or DDSOpt-optimized textures, when they can be generated on the end-user box (using exactly the same tools as you use, as all the tools and their config are just files described by *Sanguine Rose* project)?
- 🔩 automated file patch calculation and application 
- 💰 *Sanguine Rose* as such does not have problems with paid mods. Modders also deserve to get paid, you know. Keep in mind that as a modder, it is your responsibility to comply with all the other licenses (including Bethesda's one).  
- 📆 GitHub features, such as change tracking, merges, and pull requests. And it will be you deciding whether to accept pull request or not.
- 🚀 Better Performance: *Sanguine Rose* is highly paralellized, and uses some significant improvements over WJ logic. *Sanguine Rose* is apparently already faster than Wabbajack, in spite of using allegedly slow Python rather than C#. `<troll mode>` Python rulezzzz! 🥇 `</troll mode>`
- [FUTURE] an alternative way (using ReFS's CoW feature) to provide MO2-like virtual file system but without MO2 running and hooking into the game processes. It may be a bit cleaner in runtime than MO2 at the cost of longer startup and shutdown times. Will still preserve MO2 compatibility, and will make MO-like development even cleaner than MO itself (I should be able to enforce that all writes go to overwrites, ensuring that both game and mod folders always kept pristine (well, after *Sanguine Rose* restores them back 😉).

### Downsides Compared to Wabbajack

- ❌ No User Interface (UI): sanguine-rose as such is already complicated enough, and UIs are not my cup of tea either. That being said, **if you want to create a GitHub project with a UI for Sanguine Rose, that would be great!** I’m happy to support that by providing non-UI functions in Sanguine Rose, as long as your project uses a permissive license; no copyleft or other restrictions, please. This also means no stuff such as "Any quid-pro-quo payment structure in connection with... is strictly prohibited." either :angry: :rage: :scream: .


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
