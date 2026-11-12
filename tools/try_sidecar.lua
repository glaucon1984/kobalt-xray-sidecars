-- Try a sidecar against the real X-Ray plugin, outside Kobalt, with a stock Lua 5.4.
--
--   lua try_sidecar.lua <xray folder with main.lua> <sidecar as a Lua table> <percent> <word> [<word> ...]
--
-- The sidecar comes as a Lua file that returns the table (to_lua.py writes it from the JSON),
-- since stock Lua has no JSON reader. Prints the card each word would get at that position.
local folder, table_file, percent = arg[1], arg[2], tonumber(arg[3])
local data = dofile(table_file)
local logs = {}
kobalt = {
  read_sidecar = function() return "sidecar" end,
  read_file = function() return nil end,
  log = function(message) logs[#logs + 1] = message end,
  json = { decode = function() return data end },
}
dofile(folder .. "/main.lua")
book_opened({ title = "test", language = "en" })
for _, line in ipairs(logs) do print("log: " .. line) end
local function plain(html)
  return (html:gsub("</p>", "\n"):gsub("</h4>", ":\n"):gsub("<[^>]+>", "")
    :gsub("&amp;", "&"):gsub("&#39;", "'"):gsub("&quot;", '"'):gsub("&lt;", "<"):gsub("&gt;", ">"))
end
for index = 4, #arg do
  local card = before_lookup({ word = arg[index], book = {}, position = { percent = percent, page = 1, pages = 1, chapter = "" } })
  print(string.format("== %s @ %.1f%%", arg[index], percent))
  if card == nil then
    print("   (no card)")
  else
    print("   [" .. card.title .. "]  " .. card.footer)
    for line in plain(card.html):gmatch("[^\n]+") do print("   " .. line) end
    print(string.format("   html %d bytes", #card.html))
  end
end
