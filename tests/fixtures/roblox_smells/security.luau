--!nonstrict
-- security.luau — Server-side code with RemoteEvent security smells

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local DamageRemote = ReplicatedStorage:WaitForChild("DamageEvent")
local ShopRemote = ReplicatedStorage:WaitForChild("ShopEvent")
local HealRemote = ReplicatedStorage:WaitForChild("HealEvent")

local Security = {}

-- unprotected-remote: FireServer without server validation (client perspective)
-- unprotected-remote: also triggers on InvokeServer
function Security.attackEnemy(enemy)
	DamageRemote:FireServer(enemy, 25)
end

function Security.buyItem(itemId)
	local result = ShopRemote:InvokeServer(itemId)
	return result
end

-- unprotected-remote: OnServerEvent without type() validation
function Security.handleDamage(player)
	DamageRemote.OnServerEvent:Connect(function(client, target, damage)
		target.Humanoid.Health -= damage
	end)
end

-- yield-in-critical: task.wait inside OnServerEvent handler
function Security.handleHeal(player)
	HealRemote.OnServerEvent:Connect(function(client, target)
		task.wait(2)
		target.Humanoid.Health += 50
	end)
end

-- unprotected-remote: OnServerInvoke without type check
function Security.setupShop()
	ShopRemote.OnServerInvoke = function(player, itemId)
		return "purchased"
	end
end

return Security
