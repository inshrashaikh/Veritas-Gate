// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title MockToken
 * @notice Minimal, standalone ERC-20 token implementation for educational testing and demonstration.
 *
 * Denomination Specification:
 * - Decimals: 18 (Standard EVM token denomination, aligning with DAI, WETH, and governance standards).
 * - Base Unit: 1 token = 1 * 10^18 wei (1e18).
 * - Grant Reference: $5,000,000 equivalent = 5,000,000 * 10^18 (5_000_000e18 tokens).
 */
contract MockToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error InsufficientBalance(address account, uint256 available, uint256 required);
    error InsufficientAllowance(address spender, uint256 currentAllowance, uint256 needed);
    error InvalidRecipient(address recipient);

    constructor(string memory _name, string memory _symbol, uint256 _initialSupply) {
        name = _name;
        symbol = _symbol;
        if (_initialSupply > 0) {
            _mint(msg.sender, _initialSupply);
        }
    }

    /**
     * @notice Transfer tokens from caller to recipient.
     * @param to Destination address.
     * @param amount Token amount in wei (18 decimals).
     */
    function transfer(address to, uint256 amount) external returns (bool) {
        if (to == address(0)) revert InvalidRecipient(address(0));
        uint256 senderBalance = balanceOf[msg.sender];
        if (senderBalance < amount) {
            revert InsufficientBalance(msg.sender, senderBalance, amount);
        }

        unchecked {
            balanceOf[msg.sender] = senderBalance - amount;
            balanceOf[to] += amount;
        }

        emit Transfer(msg.sender, to, amount);
        return true;
    }

    /**
     * @notice Approve spender to withdraw tokens up to `amount`.
     * @param spender Allowed spender address.
     * @param amount Maximum allowed token amount.
     */
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    /**
     * @notice Transfer tokens on behalf of `from` using an existing allowance.
     * @param from Source token holder address.
     * @param to Destination address.
     * @param amount Token amount to transfer.
     */
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        if (to == address(0)) revert InvalidRecipient(address(0));
        uint256 currentAllowance = allowance[from][msg.sender];
        if (currentAllowance != type(uint256).max) {
            if (currentAllowance < amount) {
                revert InsufficientAllowance(msg.sender, currentAllowance, amount);
            }
            unchecked {
                allowance[from][msg.sender] = currentAllowance - amount;
            }
        }

        uint256 fromBalance = balanceOf[from];
        if (fromBalance < amount) {
            revert InsufficientBalance(from, fromBalance, amount);
        }

        unchecked {
            balanceOf[from] = fromBalance - amount;
            balanceOf[to] += amount;
        }

        emit Transfer(from, to, amount);
        return true;
    }

    /**
     * @notice Helper mint function for testing environments.
     * @param to Recipient of minted tokens.
     * @param amount Amount to mint.
     */
    function mint(address to, uint256 amount) external {
        if (to == address(0)) revert InvalidRecipient(address(0));
        _mint(to, amount);
    }

    function _mint(address to, uint256 amount) internal {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }
}
