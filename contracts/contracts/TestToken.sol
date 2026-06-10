// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
    function allowance(address, address) external view returns (uint256);
    function approve(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
}

contract TestToken is IERC20 {
    string public name;
    string public symbol;
    uint8  public decimals = 18;
    uint256 private _totalSupply;
    mapping(address=>uint256) private _bal;
    mapping(address=>mapping(address=>uint256)) private _allow;
    address public owner;

    constructor(string memory _name, string memory _symbol) {
        name = _name; symbol = _symbol; owner = msg.sender;
    }

    function totalSupply() external view returns (uint256) { return _totalSupply; }
    function balanceOf(address a) external view returns (uint256) { return _bal[a]; }
    function allowance(address o, address s) external view returns (uint256) { return _allow[o][s]; }

    function transfer(address to, uint256 amt) external returns (bool) {
        require(_bal[msg.sender]>=amt,"ERC20: insufficient");
        _bal[msg.sender]-=amt; _bal[to]+=amt;
        emit Transfer(msg.sender,to,amt); return true;
    }
    function approve(address s, uint256 amt) external returns (bool) {
        _allow[msg.sender][s]=amt; emit Approval(msg.sender,s,amt); return true;
    }
    function transferFrom(address from, address to, uint256 amt) external returns (bool) {
        require(_bal[from]>=amt,"ERC20: insufficient");
        require(_allow[from][msg.sender]>=amt,"ERC20: allowance");
        _allow[from][msg.sender]-=amt; _bal[from]-=amt; _bal[to]+=amt;
        emit Transfer(from,to,amt); return true;
    }
    function mint(address to, uint256 amt) external {
        _totalSupply+=amt; _bal[to]+=amt; emit Transfer(address(0),to,amt);
    }
    function faucet() external {
        uint256 amt = 1000 * 10**18;
        _totalSupply+=amt; _bal[msg.sender]+=amt; emit Transfer(address(0),msg.sender,amt);
    }
}
