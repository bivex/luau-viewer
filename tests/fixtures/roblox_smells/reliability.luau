--!nonstrict
-- reliability.luau — Reliability and correctness smells

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Reliability = {}

-- pcall-ignored-result: pcall without capturing result
function Reliability.saveData(key, value)
	pcall(function()
		print("saving")
	end)
end

-- pcall-ignored-result: xpcall without capturing
function Reliability.safeCall()
	xpcall(function()
		error("boom")
	end, function(err)
		print(err)
	end)
end

-- infinite-yield-risk: WaitForChild without timeout
function Reliability.loadModule()
	local module = ReplicatedStorage:WaitForChild("GameModule")
	require(module)
end

-- infinite-yield-risk: another case with single quotes
function Reliability.findUIElement()
	local element = script.Parent:WaitForChild("MainFrame")
end

-- unsafe-tonumber: no nil fallback
function Reliability.parseScore(input)
	local score = tonumber(input)
	print(score)
end

-- connect-leak: Connect without Maid/Disconnect
-- event-reconnect-loop: Connect inside a for loop
function Reliability.bindAllParts(parts)
	for _, part in ipairs(parts) do
		part.Touched:Connect(function(hit)
			print(hit.Name)
		end)
	end
end

-- self-assignment: variable assigns to itself
function Reliability.resetConfig(config)
	config.name = config.name
end

-- empty-function: function with empty body
function Reliability.placeholder()
end

-- unreachable: code after return
function Reliability.getStatus()
	return "active"
	print("never logged")
end

-- redundant-condition: if true
function Reliability.alwaysRun()
	if true then
		print("always")
	end
end

return Reliability
