--!strict
-- clean_module.luau — A well-written Roblox module (minimal smells)

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local MAX_REWARD = 50
local HEAL_AMOUNT = 25

type PlayerData = {
	coins: number,
	level: number,
}

local CleanModule = {}

function CleanModule.giveReward(player: Player, amount: number)
	if typeof(amount) ~= "number" or amount <= 0 then
		return
	end
	player.leaderstats.Coins.Value += amount
end

function CleanModule.healPlayer(player: Player)
	local character = player.Character
	if character == nil then
		return
	end
	local humanoid = character:FindFirstChild("Humanoid")
	if humanoid then
		humanoid.Health += HEAL_AMOUNT
	end
end

function CleanModule.loadData(player: Player): PlayerData
	local ok, result = pcall(function()
		return { coins = 100, level = 1 }
	end)
	if not ok then
		return { coins = 0, level = 1 }
	end
	return result
end

function CleanModule.parseAmount(value: string): number
	return tonumber(value) or 0
end

function CleanModule.findRemote(name: string)
	local remote = ReplicatedStorage:WaitForChild(name, 5)
	if remote == nil then
		warn("Remote not found: " .. name)
	end
	return remote
end

return CleanModule
