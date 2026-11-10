# NAS packing rules

`nas-ng.toml` holds the safety rules the NAS adds to every LZ4 NG and Zstd pack
made with PS5 Dump Forge: program, system and PlayGo files that must stay loose
on disk. A game TOML chosen in the page is merged with it; without one, Forge's
own packing rules decide the rest. There are no bundled game profiles.
