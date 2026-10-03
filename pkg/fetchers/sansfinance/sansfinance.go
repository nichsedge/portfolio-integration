package sansfinance

import (
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/nichsedge/portfolio-integration/pkg/models"
	_ "modernc.org/sqlite"
)

const (
	defaultBucketName = "ichsanul-dev"
	r2BlobName        = "db/sans_finance_latest.sqlite"
)

type AccountEntry struct {
	Name     string  `json:"name"`
	Type     string  `json:"type"`
	Balance  float64 `json:"balance"`
	Currency string  `json:"currency"`
}

type RawSansfinanceData struct {
	Accounts []AccountEntry `json:"accounts"`
}

func getSignatureKey(key, dateStamp, regionName, serviceName string) []byte {
	kDate := hmacSHA256([]byte("AWS4"+key), []byte(dateStamp))
	kRegion := hmacSHA256(kDate, []byte(regionName))
	kService := hmacSHA256(kRegion, []byte(serviceName))
	kSigning := hmacSHA256(kService, []byte("aws4_request"))
	return kSigning
}

func hmacSHA256(key []byte, data []byte) []byte {
	hash := hmac.New(sha256.New, key)
	hash.Write(data)
	return hash.Sum(nil)
}

func sha256Hex(data []byte) string {
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

// DownloadFromR2 downloads the SQLite snapshot from Cloudflare R2 using S3 SigV4.
func DownloadFromR2(accountID, accessKey, secretKey, bucket, destPath string) error {
	if bucket == "" {
		bucket = defaultBucketName
	}

	host := fmt.Sprintf("%s.r2.cloudflarestorage.com", accountID)
	endpointURL := fmt.Sprintf("https://%s/%s/%s", host, bucket, r2BlobName)

	t := time.Now().UTC()
	amzDate := t.Format("20060102T150405Z")
	dateStamp := t.Format("20060102")

	region := "auto"
	service := "s3"
	payloadHash := sha256Hex([]byte("")) // empty payload for GET

	canonicalURI := fmt.Sprintf("/%s/%s", bucket, r2BlobName)
	canonicalHeaders := fmt.Sprintf("host:%s\nx-amz-content-sha256:%s\nx-amz-date:%s\n", host, payloadHash, amzDate)
	signedHeaders := "host;x-amz-content-sha256;x-amz-date"
	canonicalRequest := fmt.Sprintf("GET\n%s\n\n%s\n%s\n%s", canonicalURI, canonicalHeaders, signedHeaders, payloadHash)

	credentialScope := fmt.Sprintf("%s/%s/%s/aws4_request", dateStamp, region, service)
	stringToSign := fmt.Sprintf("AWS4-HMAC-SHA256\n%s\n%s\n%s", amzDate, credentialScope, sha256Hex([]byte(canonicalRequest)))

	signingKey := getSignatureKey(secretKey, dateStamp, region, service)
	signature := hex.EncodeToString(hmacSHA256(signingKey, []byte(stringToSign)))

	authHeader := fmt.Sprintf("AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s",
		accessKey, credentialScope, signedHeaders, signature)

	req, err := http.NewRequest(http.MethodGet, endpointURL, nil)
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", authHeader)
	req.Header.Set("Host", host)
	req.Header.Set("x-amz-date", amzDate)
	req.Header.Set("x-amz-content-sha256", payloadHash)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		// Fallback to wrangler if direct download fails
		return downloadViaWrangler(bucket, destPath)
	}
	defer resp.Body.Close()

	_ = os.MkdirAll(filepath.Dir(destPath), 0755)
	out, err := os.Create(destPath)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, resp.Body)
	return err
}

func downloadViaWrangler(bucket, destPath string) error {
	cmd := exec.Command("wrangler", "r2", "object", "get", fmt.Sprintf("%s/%s", bucket, r2BlobName), fmt.Sprintf("--file=%s", destPath), "--remote")
	return cmd.Run()
}

// Fetch extracts cash/p2p accounts from Sans Finance SQLite.
func Fetch(accountID, accessKey, secretKey, bucket string) (*RawSansfinanceData, []models.Holding, error) {
	tmpFile, err := os.CreateTemp("", "sansfinance-*.sqlite")
	if err != nil {
		return nil, nil, err
	}
	tmpPath := tmpFile.Name()
	tmpFile.Close()
	defer os.Remove(tmpPath)

	if err := DownloadFromR2(accountID, accessKey, secretKey, bucket, tmpPath); err != nil {
		return nil, nil, fmt.Errorf("failed to download Sans Finance DB: %w", err)
	}

	db, err := sql.Open("sqlite", tmpPath)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to open Sans Finance SQLite: %w", err)
	}
	defer db.Close()

	query := "SELECT name, type, balance, currency FROM accounts WHERE type IN ('Cash', 'Bank Account', 'P2P Lending')"
	rows, err := db.Query(query)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to query accounts: %w", err)
	}
	defer rows.Close()

	var accounts []AccountEntry
	for rows.Next() {
		var name, accType, curr string
		var balanceCents float64
		if err := rows.Scan(&name, &accType, &balanceCents, &curr); err != nil {
			continue
		}
		if curr == "" {
			curr = "IDR"
		}
		accounts = append(accounts, AccountEntry{
			Name:     name,
			Type:     accType,
			Balance:  balanceCents / 100.0,
			Currency: curr,
		})
	}

	raw := &RawSansfinanceData{Accounts: accounts}
	holdings := Standardize(raw)
	return raw, holdings, nil
}

// Standardize converts accounts into standardized portfolio holdings.
func Standardize(data *RawSansfinanceData) []models.Holding {
	var holdings []models.Holding

	for _, acc := range data.Accounts {
		balance := acc.Balance
		if math.Abs(balance) < 1.0 {
			continue
		}

		currency := acc.Currency
		var category string
		var valIDR, valUSD *float64

		if balance < 0 {
			category = "Liabilities"
			posVal := -balance
			if currency == "IDR" {
				valIDR = &posVal
			} else {
				valUSD = &posVal
			}
		} else {
			if acc.Type == "P2P Lending" {
				category = "P2P Lending"
			} else if acc.Type == "Cash" {
				category = "Digital Bank"
			} else {
				category = "Bank Account"
			}
			if currency == "IDR" {
				valIDR = &balance
			} else {
				valUSD = &balance
			}
		}

		price := 1.0
		holdings = append(holdings, models.Holding{
			Source:     "SansFinance",
			Category:   category,
			Asset:      acc.Name,
			Name:       acc.Name,
			Currency:   currency,
			Quantity:   0,
			Price:      &price,
			PriceIDR:   &price,
			ValueIDR:   valIDR,
			ValueUSD:   valUSD,
			Account:    acc.Name,
			Details:    fmt.Sprintf("Type: %s", acc.Type),
			AssetClass: models.GetAssetClass(category),
		})
	}

	return holdings
}

// SaveRaw dumps raw Sans Finance data to disk.
func SaveRaw(data *RawSansfinanceData, targetPath string) error {
	_ = os.MkdirAll(filepath.Dir(targetPath), 0755)
	b, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(targetPath, b, 0644)
}
