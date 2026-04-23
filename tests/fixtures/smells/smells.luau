-- Triggers: deprecated-api, empty-function, infinite-loop, wait-in-loop
-- Also triggers: magic-numbers, global-variable, instance-in-loop,
--                getchildren-in-loop, unprotected-remote, connect-leak,
--                pcall-ignored-result, infinite-yield-risk, unsafe-tonumber

local REWARD_COINS = 15

local Smells = {}

function Smells.empty()
end

function Smells.process(items)
	spawn(function()
		print("started")
	end)
	wait(0.1)
	while true do
		local x = 1
	end
	for i = 1, 10 do
		task.wait(1)
	end
	return items
end

function Smells.nested(x)
	if x > 0 then
		if x > 10 then
			if x > 20 then
				if x > 30 then
					if x > 40 then
						return x
					end
				end
			end
		end
	end
	return 0
end

function Smells.unreachable()
	return 1
	print("never reached")
end

function Smells.rewards(player)
	player.leaderstats.Coins.Value += 15
end

function Smells.globalState()
	_G.PlayerData = {}
end

function Smells.spawnParts()
	for i = 1, 10 do
		local part = Instance.new("Part")
		part.Parent = workspace
	end
end

function Smells.pollChildren()
	while true do
		local children = workspace:GetChildren()
		break
	end
end

function Smells.attackEnemy(enemy)
	DamageRemote:FireServer(enemy, 25)
end

function Smells.onCharacterAdded(player)
	player.CharacterAdded:Connect(function(character)
		print("Character loaded")
	end)
end

function Smells.riskyCall()
	pcall(function()
		DataStore:SetAsync("key", {})
	end)
end

function Smells.loadChild()
	local obj = ReplicatedStorage:WaitForChild("DamageEvent")
end

function Smells.parseInput(value)
	local n = tonumber(value)
end

return Smells
