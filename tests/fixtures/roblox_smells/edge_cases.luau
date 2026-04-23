--!nonstrict
-- edge_cases.luau — triggers the 5 rules missed by other fixture files

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local EdgeCases = {}

-- infinite-loop: while true without break or return
function EdgeCases.runForever()
	while true do
		local x = 1
	end
end

-- long-function: exceeds 50 steps
function EdgeCases.megaFunction()
	local a = 1
	local b = 2
	local c = 3
	local d = 4
	local e = 5
	local f = 6
	local g = 7
	local h = 8
	local i = 9
	local j = 10
	local k = 11
	local l = 12
	local m = 13
	local n = 14
	local o = 15
	local p = 16
	local q = 17
	local r = 18
	local s = 19
	local t = 20
	local u = 21
	local v = 22
	local w = 23
	local x = 24
	local y = 25
	local z = 26
	local aa = 27
	local ab = 28
	local ac = 29
	local ad = 30
	local ae = 31
	local af = 32
	local ag = 33
	local ah = 34
	local ai = 35
	local aj = 36
	local ak = 37
	local al = 38
	local am = 39
	local an = 40
	local ao = 41
	local ap = 42
	local aq = 43
	local ar = 44
	local as = 45
	local at = 46
	local au = 47
	local av = 48
	local aw = 49
	local ax = 50
	local ay = 51
end

-- nested-closures (inlined by ANTLR): task.spawn wrapping task.delay
function EdgeCases.callbackHell()
	task.spawn(function()
		task.delay(1, function()
			print("deeply nested")
		end)
	end)
end

-- yield-in-critical + unprotected-remote (inlined by ANTLR)
function EdgeCases.handleRemoteInlined()
	ReplicatedStorage.DamageEvent.OnServerEvent:Connect(function(player, damage)
		task.wait(2)
		print("processed")
	end)
end

-- event-reconnect-loop (inlined by ANTLR): :Connect inside for loop
function EdgeCases.bindAllPartsInlined(parts)
	for _, part in ipairs(parts) do
		part.Touched:Connect(function(hit)
			print(hit.Name)
		end)
	end
end

return EdgeCases
