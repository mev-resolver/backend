const { ethers } = require('hardhat');

async function main() {
  const [dep] = await ethers.getSigners();
  console.log('Deployer:', dep.address);
  const bal = await ethers.provider.getBalance(dep.address);
  console.log('Balance:', ethers.formatEther(bal), 'ETH');

  const Token = await ethers.getContractFactory('TestToken');
  const res = await Token.deploy('Resolver Token', 'RES');
  await res.waitForDeployment();
  console.log('RES:', await res.getAddress());

  const olv = await Token.deploy('Olive Token', 'OLV');
  await olv.waitForDeployment();
  console.log('OLV:', await olv.getAddress());

  const DEX = await ethers.getContractFactory('ResolverDEX');
  const dex = await DEX.deploy();
  await dex.waitForDeployment();
  console.log('DEX:', await dex.getAddress());

  await (await dex.createPair(await res.getAddress(), await olv.getAddress())).wait();
  console.log('Pair created');

  const liq = ethers.parseEther('10000');
  await (await res.mint(dep.address, liq)).wait();
  await (await olv.mint(dep.address, liq)).wait();
  await (await res.approve(await dex.getAddress(), liq)).wait();
  await (await olv.approve(await dex.getAddress(), liq)).wait();
  await (await dex.addLiquidity(await res.getAddress(), await olv.getAddress(), liq, liq)).wait();
  console.log('Liquidity: 10000 RES + 10000 OLV');

  console.log('\n=== Add to .env ===');
  console.log('TOKEN_RES_ADDRESS=' + await res.getAddress());
  console.log('TOKEN_OLV_ADDRESS=' + await olv.getAddress());
  console.log('DEX_CONTRACT_ADDRESS=' + await dex.getAddress());
}

main().catch(e => { console.error(e); process.exit(1); });
